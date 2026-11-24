"""Bounded opt-in Python frame-call observations for vetted HIT generators.

Reuse P1 capture and canonical Python AST identities. Only current-thread
CPython events at explicitly selected call sites are recorded. No imports,
arbitrary execution, tracing of secret values, Native observations or proof
of unexecuted branches. Run/job context is caller supplied, not attested.
"""
from __future__ import annotations

from dataclasses import dataclass
import dis
from hashlib import sha256
import inspect
import json
import math
import re
import sys
from time import monotonic
from types import FunctionType

from ..diagnostics.collector import (
    CollectionResult, FactBatch, graph_edge_id, scan_scope_id, stable_id,
)
from ..diagnostics.providers.python_ast import PythonAstCollector, python_call_site_id
from ..diagnostics.providers.git import GitSourceProvider
from ..diagnostics.request import ScanRequest
from ..graph import Edge, Evidence
from .generated_input_actions import (
    GeneratedCapture, capture_generated_return, verify_loaded_python_function,
)


@dataclass(frozen=True, slots=True)
class SelectedPythonFunction:
    path: str
    blob_sha: str
    function: FunctionType
    hash_arguments: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PythonCallTrace:
    capture: GeneratedCapture
    result: CollectionResult

    @property
    def independently_authenticated(self) -> bool:
        return False


def _symbol_id(repository, selected):
    return stable_id("node", repository, "python_symbol", selected.path,
                     selected.function.__name__)


def _frame_key(frame):
    return id(frame.f_code), id(frame.f_globals)


def _function_key(function):
    return id(function.__code__), id(function.__globals__)


def _argument_hash(frame, names):
    if not names:
        return ""
    values = {}
    for name in names:
        value = frame.f_locals[name]
        if (type(value) not in (type(None), bool, int, float, str)
                or (type(value) is str and len(value) > 4096)
                or (type(value) is int and value.bit_length() > 256)
                or (type(value) is float and not math.isfinite(value))):
            raise ValueError("PYTHON_TRACE_ARGUMENT_UNSUPPORTED")
        values[name] = value
    data = json.dumps(values, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(data) > 64_000:
        raise ValueError("PYTHON_TRACE_ARGUMENT_BUDGET")
    return sha256(data).hexdigest()


def _trace_ref(attrs):
    return (f"python-trace://{attrs['repository']}/{attrs['run_id']}/"
            f"{attrs['attempt']}/{attrs['job_id']}/{attrs['trace_id']}/"
            f"{attrs['event_index']}")


def _trace_evidence_id(scope_id, attrs):
    return stable_id("evidence", scope_id, "python-frame-call-v0.1", dict(attrs))


def trace_generated_calls(
    request: ScanRequest, provider: GitSourceProvider, *,
    entry: SelectedPythonFunction, functions: tuple[SelectedPythonFunction, ...],
    site_ids: tuple[str, ...], trace_id: str, arguments: dict,
    artifact_path: str, run_id: int, attempt: int, job_id: int,
    workflow_path: str, max_events: int = 128,
) -> PythonCallTrace:
    """Execute one explicitly authorized text-returning generator via P1c.

    Select actual caller/callee functions and canonical AST call-site IDs.
    Profile only the current thread; refuse an existing profiler/tracer.
    Observe a direct Python frame transition at an exact bytecode position,
    not a proof of semantic dispatch or of all possible callees. Builtins,
    C callbacks, unselected targets and sites not observed remain unresolved.
    Event cap bounds retained observations, not execution; time is checked
    after the call, not a hard timeout. The caller must vet the code, use a
    governed environment and explicitly opt in only non-secret arguments.
    """
    started = monotonic()
    if sys.implementation.name != "cpython" or sys.version_info < (3, 11):
        raise ValueError("PYTHON_TRACE_INTERPRETER_UNSUPPORTED")
    if sys.getprofile() is not None or sys.gettrace() is not None:
        raise ValueError("PYTHON_TRACE_EXISTING_HOOK")
    if (not isinstance(entry, SelectedPythonFunction)
            or type(functions) is not tuple or not functions
            or any(not isinstance(x, SelectedPythonFunction) for x in functions)
            or not any(x is entry for x in functions) or len(functions) > 32):
        raise ValueError("PYTHON_TRACE_FUNCTION_SELECTION_INVALID")
    if (type(site_ids) is not tuple or not site_ids or len(site_ids) > 64
            or any(not isinstance(x, str) or not re.fullmatch(r"node:[0-9a-f]{64}", x)
                   for x in site_ids) or len(set(site_ids)) != len(site_ids)
            or not isinstance(trace_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", trace_id)
            or type(max_events) is not int or not 1 <= max_events <= 256
            or "python_ast" not in request.collectors):
        raise ValueError("PYTHON_TRACE_SITE_SELECTION_INVALID")
    scope_id = scan_scope_id(request)
    keys = {}
    sources = {}
    owner_sites = {}
    source_bytes = 0
    for selected in functions:
        function = selected.function
        source = verify_loaded_python_function(
            request, provider, selected.path, selected.blob_sha, function)
        key = _function_key(function)
        if key in keys or any(_symbol_id(request.repository, x) ==
                              _symbol_id(request.repository, selected) for x in keys.values()):
            raise ValueError("PYTHON_TRACE_DUPLICATE_FUNCTION")
        names = selected.hash_arguments
        if (type(names) is not tuple or len(names) > 16
                or any(type(n) is not str for n in names) or len(set(names)) != len(names)
                or any(n not in inspect.signature(function, follow_wrapped=False).parameters
                       for n in names)):
            raise ValueError("PYTHON_TRACE_ARGUMENT_SELECTION_INVALID")
        keys[key] = selected
        if selected.path not in sources:
            source_bytes += len(source.content)
            if (len(sources) >= request.budget.max_files
                    or source_bytes > request.budget.max_bytes):
                raise ValueError("PYTHON_TRACE_SOURCE_BUDGET")
            facts = PythonAstCollector().collect(source, request, scope_id)
            sources[selected.path] = facts.batch
        facts = sources[selected.path]
        owner = _symbol_id(request.repository, selected)
        if not any(n.id == owner and n.kind == "python_function" for n in facts.nodes):
            raise ValueError("PYTHON_TRACE_SYMBOL_UNRESOLVED")
        owner_sites[key] = {e.target_id for e in facts.edges
                            if e.source_id == owner and e.relation == "CALLS_CANDIDATE"}
    allowed = set(site_ids)
    if not allowed <= set().union(*owner_sites.values()):
        raise ValueError("PYTHON_TRACE_SITE_NOT_IN_SELECTED_SOURCE")
    positions = {}
    for key, selected in keys.items():
        offsets = {}
        for instruction in dis.get_instructions(selected.function, show_caches=True):
            if not (instruction.opname.startswith(("CALL", "PRECALL"))
                    or instruction.opname == "CACHE"):
                continue
            p = instruction.positions
            if p is None or None in (p.lineno, p.col_offset, p.end_lineno, p.end_col_offset):
                continue
            span = (p.lineno, p.col_offset, p.end_lineno, p.end_col_offset)
            site = python_call_site_id(request.repository, selected.path, *span)
            if site in allowed and site in owner_sites[key]:
                offsets[instruction.offset] = (site, span)
        positions[key] = offsets
    pending_c = set()
    unresolved = {"PYTHON_TRACE_RUNNER_CONTEXT_UNAUTHENTICATED",
                  "PYTHON_TRACE_UNSELECTED_EXECUTION_AND_BRANCHES_UNPROVEN"}
    observed = []
    seen = set()
    events = 0

    def location(frame):
        return positions.get(_frame_key(frame), {}).get(frame.f_lasti)

    def profile(frame, event, arg):
        nonlocal events
        if event in {"c_return", "c_exception"}:
            pending_c.discard(id(frame))
            return
        if event not in {"call", "c_call"}:
            return
        caller = frame.f_back if event == "call" else frame
        if caller is None:
            return
        matched = location(caller)
        if matched is None:
            return
        site, span = matched
        if events >= max_events:
            unresolved.add("PYTHON_TRACE_EVENT_BUDGET_EXCEEDED")
            return
        events += 1
        if event == "c_call":
            pending_c.add(id(caller))
            unresolved.add("PYTHON_TRACE_C_CALL_UNSUPPORTED:" + site)
            return
        if id(caller) in pending_c:
            unresolved.add("PYTHON_TRACE_C_CALLBACK_UNSUPPORTED:" + site)
            return
        callee = keys.get(_frame_key(frame))
        if callee is None:
            unresolved.add("PYTHON_TRACE_UNSELECTED_CALLEE:" + site)
            return
        seen.add(site)
        try:
            arg_digest = _argument_hash(frame, callee.hash_arguments)
        except (ValueError, KeyError):
            arg_digest = ""
            unresolved.add("PYTHON_TRACE_ARGUMENT_UNRESOLVED:" + site)
        observed.append((events, site, span, keys[_frame_key(caller)], callee, arg_digest))

    if monotonic() - started > request.budget.max_seconds:
        raise ValueError("PYTHON_TRACE_TIME_BUDGET")
    sys.setprofile(profile)
    try:
        capture = capture_generated_return(
            request, provider, producer_path=entry.path, producer_blob_sha=entry.blob_sha,
            function=entry.function, arguments=arguments, artifact_path=artifact_path,
            run_id=run_id, attempt=attempt, job_id=job_id, workflow_path=workflow_path)
        if sys.getprofile() is not profile:
            raise ValueError("PYTHON_TRACE_HOOK_CHANGED")
    finally:
        sys.setprofile(None)
    for key, selected in keys.items():
        verify_loaded_python_function(request, provider, selected.path,
                                      selected.blob_sha, selected.function)
        if _function_key(selected.function) != key:
            raise ValueError("PYTHON_TRACE_FUNCTION_CHANGED")
    if monotonic() - started > request.budget.max_seconds:
        raise ValueError("PYTHON_TRACE_TIME_BUDGET")
    unresolved.update("PYTHON_TRACE_SITE_NOT_OBSERVED:" + site for site in allowed - seen)
    identity = json.loads(capture.manifest)["identity"]
    evidence, edges = [], []
    for index, site, span, caller, callee, arg_digest in observed:
        target = _symbol_id(request.repository, callee)
        attrs = {
            "repository": request.repository, "source_sha": request.revision,
            "run_id": run_id, "attempt": attempt, "job_id": job_id,
            "trace_id": trace_id, "event_index": index,
            "context": "CALLER_SUPPLIED", "site_id": site, "callee_id": target,
            "caller_path": caller.path, "caller_blob_sha": caller.blob_sha,
            "caller_symbol": caller.function.__name__, "position": span,
            "callee_path": callee.path, "callee_blob_sha": callee.blob_sha,
            "callee_symbol": callee.function.__name__, "argument_sha256": arg_digest,
            "invocation_sha256": identity["invocation_sha256"],
            "hit_sha256": identity["artifact_sha256"],
        }
        ref = _trace_ref(attrs)
        attrs["url"] = ref  # Local trace URI, not an authenticated external URL.
        eid = _trace_evidence_id(scope_id, attrs)
        evidence.append(Evidence(
            id=eid, kind="PYTHON_CALL_TRACE", source_ref=ref,
            method="python-frame-call-v0.1", scope_id=scope_id,
            observation_status="RUNTIME_OBSERVED", attributes=attrs))
        edges.append(Edge(
            id=graph_edge_id(site, target, "PYTHON_FRAME_CALL_OBSERVED", eid),
            source_id=site, target_id=target, relation="PYTHON_FRAME_CALL_OBSERVED",
            discriminator=eid, evidence_ids=(eid,)))
    return PythonCallTrace(capture, CollectionResult(
        FactBatch(edges=tuple(edges), evidence=tuple(evidence),
                  unresolved=tuple(sorted(unresolved))), status="PARTIAL"))


def validate_python_trace_metadata(evidence, scope, paths, nodes, edges, witnesses):
    """Validate Graph/receipt binding only; never attest execution from metadata."""
    a = evidence.attributes
    if (evidence.observation_status != "RUNTIME_OBSERVED"
            or evidence.method != "python-frame-call-v0.1"
            or a["repository"] != scope.repository or a["source_sha"] != scope.revision
            or a["context"] != "CALLER_SUPPLIED"
            or any(type(a[k]) is not int or a[k] < 1
                   for k in ("run_id", "attempt", "job_id", "event_index"))
            or a["event_index"] > 256
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", a["trace_id"])
            or evidence.source_ref != _trace_ref(a) or a["url"] != evidence.source_ref
            or evidence.id != _trace_evidence_id(scope.id, a)):
        raise ValueError("PYTHON_TRACE_CONTEXT_INVALID")
    for field in ("invocation_sha256", "hit_sha256", "argument_sha256"):
        if field == "argument_sha256" and a[field] == "":
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", a[field]):
            raise ValueError("PYTHON_TRACE_DIGEST_INVALID")
    for prefix in ("caller", "callee"):
        item = paths[a[prefix + "_path"]]
        if (item.status not in {"SCANNED", "UNRESOLVED"} or item.blob_sha != a[prefix + "_blob_sha"]
                or "python_ast" not in item.collectors):
            raise ValueError("PYTHON_TRACE_SOURCE_INVALID")
    span = a["position"]
    if (len(span) != 4 or any(type(n) is not int for n in span)
            or span[0] < 1 or span[2] < span[0] or min(span[1], span[3]) < 0
            or (span[0] == span[2] and span[3] <= span[1])):
        raise ValueError("PYTHON_TRACE_POSITION_INVALID")
    site = python_call_site_id(scope.repository, a["caller_path"], *span)
    caller = stable_id("node", scope.repository, "python_symbol",
                       a["caller_path"], a["caller_symbol"])
    callee = stable_id("node", scope.repository, "python_symbol",
                       a["callee_path"], a["callee_symbol"])
    if (a["site_id"] != site or a["callee_id"] != callee
            or nodes[site].kind != "python_call_site"
            or nodes[site].location.path != a["caller_path"]
            or nodes[site].location.start_line != span[0]
            or nodes[caller].kind != "python_function"
            or nodes[callee].kind != "python_function"
            or not any(e.source_id == caller and e.target_id == site
                       and e.relation == "CALLS_CANDIDATE" for e in edges)):
        raise ValueError("PYTHON_TRACE_ENDPOINT_INVALID")
    for node_id, prefix in ((site, "caller"), (caller, "caller"), (callee, "callee")):
        if not any(
                witnesses[eid].observation_status == "SOURCE_DECLARED"
                and witnesses[eid].attributes.get("path") == a[prefix + "_path"]
                and witnesses[eid].attributes.get("blob_sha") == a[prefix + "_blob_sha"]
                and witnesses[eid].attributes.get("source_sha") == scope.revision
                for eid in nodes[node_id].evidence_ids):
            raise ValueError("PYTHON_TRACE_SOURCE_WITNESS_MISSING")
    matches = [e for e in edges if evidence.id in e.evidence_ids]
    if (len(matches) != 1 or matches[0].source_id != site
            or matches[0].target_id != callee
            or matches[0].relation != "PYTHON_FRAME_CALL_OBSERVED"
            or matches[0].discriminator != evidence.id
            or matches[0].id != graph_edge_id(site, callee, matches[0].relation, evidence.id)):
        raise ValueError("PYTHON_TRACE_EDGE_INVALID")


__all__ = ["SelectedPythonFunction", "PythonCallTrace", "trace_generated_calls"]
