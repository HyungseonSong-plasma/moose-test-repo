"""P2: observe real selected Python frame transitions, never global closure."""
from dataclasses import replace
from hashlib import sha256
import importlib.util
import json
import sys

import pytest

from physics_harness.code.diagnostics import (
    FactBatch, GitSourceProvider, GraphAssembler, ScanRequest, run_scan,
)
from physics_harness.code.diagnostics.providers.generated_input import (
    GeneratedInputIdentity, collect_generated_input,
)
from physics_harness.code.verification.consistency import verify_generated_artifact
from physics_harness.code.verification.python_call_trace import (
    SelectedPythonFunction, trace_generated_calls,
)


SOURCE = """
def alpha(kind):
    return '[Kernels]\\n [./k]\\n type = ' + kind + '\\n [../]\\n[]\\n'

def beta(kind):
    return alpha(kind)

def entry(choice, kind='MyKernel'):
    if choice == 'cold':
        return beta(kind)
    fn = alpha if choice == 'a' else beta
    return fn(kind)
"""
PATH = "src/producer.py"
WORKFLOW = ".github/workflows/example.yml"


def scenario(git_factory, source=SOURCE, names=("entry", "alpha", "beta")):
    root, revision = git_factory({PATH: source})
    request = ScanRequest("example/repo", revision, (PATH,), collectors=("python_ast",))
    provider = GitSourceProvider(root)
    blob = provider.read_at_revision(revision, PATH).record.blob_sha
    spec = importlib.util.spec_from_file_location("selected_trace_fixture", root / PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    selected = tuple(SelectedPythonFunction(
        PATH, blob, getattr(module, name),
        ("kind",) if name in {"alpha", "beta"} else ()) for name in names)
    baseline = run_scan(request, provider)
    sites = tuple(n for n in baseline.graph.nodes if n.kind == "python_call_site")
    return request, provider, selected, baseline, sites


def observe(s, *, args=None, site_ids=None, trace_id="one", max_events=128, functions=None):
    request, provider, selected, _, sites = s
    return trace_generated_calls(
        request, provider, entry=selected[0],
        functions=selected if functions is None else functions,
        site_ids=tuple(n.id for n in sites) if site_ids is None else site_ids,
        trace_id=trace_id, arguments={"choice": "a"} if args is None else args,
        artifact_path="inputs/generated.i", run_id=10, attempt=1, job_id=21,
        workflow_path=WORKFLOW, max_events=max_events)


def combined(s, *traces):
    request, provider, _, baseline, _ = s
    graph = baseline.graph
    base = FactBatch(nodes=graph.nodes, edges=graph.edges,
                     evidence=graph.evidence, unresolved=graph.scope.unresolved)
    return GraphAssembler().assemble(
        request, (base, *(t.result.batch for t in traces)), baseline.receipt)


def test_alias_dispatch_same_ast_site_different_observed_target(git_factory):
    s = scenario(git_factory)
    first = observe(s, trace_id="alpha")
    second = observe(s, args={"choice": "b"}, trace_id="beta")
    site = next(n for n in s[-1] if n.name == "fn")
    a = next(e for e in first.result.batch.evidence if e.attributes["site_id"] == site.id)
    b = next(e for e in second.result.batch.evidence if e.attributes["site_id"] == site.id)
    assert a.attributes["callee_symbol"] == "alpha"
    assert b.attributes["callee_symbol"] == "beta"
    assert a.attributes["callee_id"] != b.attributes["callee_id"]
    assert a.attributes["argument_sha256"] == sha256(b'{"kind":"MyKernel"}').hexdigest()
    assert "MyKernel" not in json.dumps(dict(a.attributes))
    assert first.capture.hit == second.capture.hit
    assert a.attributes["hit_sha256"] == sha256(first.capture.hit).hexdigest()
    assert a.attributes["invocation_sha256"] != b.attributes["invocation_sha256"]
    assert a.observation_status == "RUNTIME_OBSERVED"
    assert a.attributes["context"] == "CALLER_SUPPLIED"
    assert not first.independently_authenticated
    full = combined(s, first, second)
    assert full.status == "PARTIAL" and full.verification.status == "UNVERIFIED"
    assert not full.verification.failures
    assert len([e for e in full.graph.edges
                if e.relation == "PYTHON_FRAME_CALL_OBSERVED"]) == 3


def test_unexecuted_site_is_not_a_negative_reference(git_factory):
    s = scenario(git_factory)
    observed = observe(s)
    cold = next(n for n in s[-1] if n.name == "beta")
    assert "PYTHON_TRACE_SITE_NOT_OBSERVED:" + cold.id in observed.result.batch.unresolved
    assert not any(e.attributes["site_id"] == cold.id for e in observed.result.batch.evidence)


def test_trace_and_generated_hit_share_invocation_and_output_digest(git_factory):
    s = scenario(git_factory)
    request, provider, _, baseline, _ = s
    trace = observe(s)
    identity = GeneratedInputIdentity(
        **json.loads(trace.capture.manifest)["identity"], artifact_id=20)
    generated = collect_generated_input(
        request, provider, expected=identity, receipt=identity, content=trace.capture.hit)
    graph = baseline.graph
    base = FactBatch(nodes=graph.nodes, edges=graph.edges,
                     evidence=graph.evidence, unresolved=graph.scope.unresolved)
    full = GraphAssembler().assemble(
        request, (base, trace.result.batch, generated.batch), baseline.receipt)
    assert not full.verification.failures and full.status == "PARTIAL"
    assert any(e.relation == "GENERATED_DECLARES_TYPE_USE" for e in full.graph.edges)
    assert all(e.attributes["hit_sha256"] == identity.artifact_sha256 and
               e.attributes["invocation_sha256"] == identity.invocation_sha256
               for e in trace.result.batch.evidence)


def test_same_line_calls_do_not_collapse(git_factory):
    s = scenario(git_factory, """
def alpha(kind): return kind
def beta(kind): return kind
def entry(choice, kind='MyKernel'): return alpha(kind) + beta(kind)
""")
    trace = observe(s)
    ev = trace.result.batch.evidence
    assert len(ev) == 2
    assert len({e.attributes["site_id"] for e in ev}) == 2
    assert {e.attributes["callee_symbol"] for e in ev} == {"alpha", "beta"}
    assert not combined(s, trace).verification.failures


def test_event_cap_and_unselected_callee_are_partial(git_factory):
    s = scenario(git_factory, """
def alpha(kind): return kind
def beta(kind): return kind
def entry(choice, kind='MyKernel'):
    out = ''
    for i in range(4):
        out += alpha(kind)
    return out + beta(kind)
""")
    trace = observe(s, max_events=2, site_ids=tuple(n.id for n in s[-1] if n.name != "range"))
    assert len(trace.result.batch.evidence) == 2
    assert "PYTHON_TRACE_EVENT_BUDGET_EXCEEDED" in trace.result.batch.unresolved
    target = next(n for n in s[-1] if n.name == "beta")
    trace = observe(s, functions=s[2][:2], site_ids=(target.id,))
    assert not trace.result.batch.evidence
    assert "PYTHON_TRACE_UNSELECTED_CALLEE:" + target.id in trace.result.batch.unresolved


def test_unsupported_argument_is_not_serialized(git_factory):
    s = scenario(git_factory, """
def alpha(kind): return 'generated'
def beta(kind): return kind
def entry(choice, kind='MyKernel'): return alpha([kind])
""")
    trace = observe(s)
    ev, = trace.result.batch.evidence
    assert ev.attributes["argument_sha256"] == ""
    assert any(x.startswith("PYTHON_TRACE_ARGUMENT_UNRESOLVED:") for x in trace.result.batch.unresolved)


def test_c_callback_not_misclassified_as_direct_callee(git_factory):
    s = scenario(git_factory, """
def alpha(kind): return kind
def beta(kind): return kind
def entry(choice, kind='MyKernel'): return ''.join(sorted([kind], key=alpha))
""")
    trace = observe(s)
    assert not trace.result.batch.evidence
    assert any(x.startswith("PYTHON_TRACE_C_CALL_UNSUPPORTED:") for x in trace.result.batch.unresolved)


def test_invalid_site_and_wrong_blob_rejected_before_execution(git_factory):
    s = scenario(git_factory)
    with pytest.raises(ValueError, match="PYTHON_TRACE_SITE_NOT_IN_SELECTED_SOURCE"):
        observe(s, site_ids=("node:" + "0" * 64,))
    bad = replace(s[2][1], blob_sha="f" * 40)
    with pytest.raises(ValueError, match="GENERATED_PRODUCER_BLOB_MISMATCH"):
        observe(s, functions=(s[2][0], bad, s[2][2]))


def test_existing_profile_refused_and_not_replaced(git_factory):
    s = scenario(git_factory)
    def existing(frame, event, arg):
        pass
    sys.setprofile(existing)
    try:
        with pytest.raises(ValueError, match="PYTHON_TRACE_EXISTING_HOOK"):
            observe(s)
        assert sys.getprofile() is existing
    finally:
        sys.setprofile(None)


def test_profile_removed_after_generator_exception(git_factory):
    s = scenario(git_factory, """
def alpha(kind): raise RuntimeError('deliberate')
def beta(kind): return kind
def entry(choice, kind='MyKernel'): return alpha(kind)
""")
    with pytest.raises(RuntimeError, match="deliberate"):
        observe(s)
    assert sys.getprofile() is None


@pytest.mark.parametrize("field,value", [
    ("callee_blob_sha", "a" * 40), ("site_id", "node:" + "b" * 64),
    ("attempt", 2), ("hit_sha256", "c" * 64),
])
def test_trace_metadata_tamper_fails_verification(git_factory, field, value):
    s = scenario(git_factory)
    full = combined(s, observe(s))
    ev = next(e for e in full.graph.evidence if e.kind == "PYTHON_CALL_TRACE")
    bad = replace(ev, attributes={**dict(ev.attributes), field: value})
    graph = replace(full.graph, evidence=tuple(
        bad if e.id == ev.id else e for e in full.graph.evidence))
    result = verify_generated_artifact(graph, full.receipt)
    assert result.status == "FAILED"
    assert "PYTHON_TRACE_PROVENANCE_INVALID:" + ev.id in result.failures
