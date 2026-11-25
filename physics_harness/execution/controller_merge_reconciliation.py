"""Read-only, conservative reconciliation of independent PR candidates.

Trusted ports must authenticate complete immutable Git trees, enrollment,
record ancestry, source receipts and integration evidence. No merge, writes,
state transitions or execution authorization. Common-baseline, disjoint (or
identical) file changes only; semantic resolutions need a separate review.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from types import MappingProxyType

from .controller_pr_state import PRBinding, validate_bindings, PRStateHold

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_STATE_ROOT = "automation/controller-state/"
_MODES = {"100644", "100755", "120000", "160000"}
_REQUIRED_GATES = {"semantic_compatibility", "integrated_validation"}
_MAX_FILES = 200_000
_MAX_RECORDS = 10_000
_MAX_RECORD_BYTES = 1_000_000


def _valid(value, pattern):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _path(path):
    return (isinstance(path, str) and bool(path) and not any(ord(c) < 32 for c in path)
            and "\\" not in path and all(p not in {"", ".", "..", ".git"}
                                         for p in path.split("/")))


@dataclass(frozen=True, slots=True)
class TreeEntry:
    mode: str
    sha256: str

    def __post_init__(self):
        if self.mode not in _MODES or not _valid(self.sha256, _DIGEST):
            raise PRStateHold("INVALID_TREE_ENTRY")


@dataclass(frozen=True, slots=True)
class TreeSnapshot:
    head: str
    entries: Mapping[str, TreeEntry]

    def __post_init__(self):
        if (not _valid(self.head, _SHA) or not isinstance(self.entries, Mapping)
                or len(self.entries) > _MAX_FILES):
            raise PRStateHold("INVALID_TREE_SNAPSHOT")
        entries = dict(self.entries)
        if any(not _path(p) or not isinstance(e, TreeEntry) for p, e in entries.items()):
            raise PRStateHold("INVALID_TREE_INVENTORY")
        for path in entries:
            parts = path.split("/")
            if any("/".join(parts[:i]) in entries for i in range(1, len(parts))):
                raise PRStateHold("TREE_FILE_DIRECTORY_COLLISION")
        object.__setattr__(self, "entries", MappingProxyType(entries))


@dataclass(frozen=True, slots=True)
class UnitRequirement:
    unit_id: str
    input_sha256: str

    def __post_init__(self):
        if (not isinstance(self.unit_id, str) or not self.unit_id.strip()
                or not _valid(self.input_sha256, _DIGEST)):
            raise PRStateHold("INVALID_WORK_UNIT")


@dataclass(frozen=True, slots=True)
class PRMergeSource:
    binding: PRBinding
    base_head: str
    tree: TreeSnapshot
    initial_revision: int
    initial_record_sha256: str
    plan_sha256: str
    policy_sha256: str
    required_units: tuple[UnitRequirement, ...]
    records: Mapping[str, bytes]

    def __post_init__(self):
        if (not isinstance(self.binding, PRBinding) or not _valid(self.base_head, _SHA)
                or not isinstance(self.tree, TreeSnapshot)
                or type(self.initial_revision) is not int
                or not 0 <= self.initial_revision < 10**16 - 1
                or any(not _valid(x, _DIGEST) for x in (self.initial_record_sha256,
                                                       self.plan_sha256, self.policy_sha256))
                or not isinstance(self.required_units, tuple) or not self.required_units
                or len(self.required_units) > 4096
                or any(not isinstance(u, UnitRequirement) for u in self.required_units)
                or len({u.unit_id for u in self.required_units}) != len(self.required_units)
                or not isinstance(self.records, Mapping) or not 0 < len(self.records) <= _MAX_RECORDS):
            raise PRStateHold("INVALID_SOURCE_EVIDENCE")
        records = dict(self.records)
        if any(not _path(p) or not isinstance(b, bytes) or not 0 < len(b) <= _MAX_RECORD_BYTES
               for p, b in records.items()):
            raise PRStateHold("INVALID_SOURCE_RECORDS")
        object.__setattr__(self, "records", MappingProxyType(records))


@dataclass(frozen=True, slots=True)
class GateEvidence:
    gate: str
    candidate_head: str
    outcome: str
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class MergeReconciliation:
    status: str
    reasons: tuple[str, ...]
    source_heads: tuple[str, ...]
    candidate_head: str
    preserved_records: int = 0
    covered_units: int = 0

    @property
    def merge_authorized(self) -> bool:
        return False

    @property
    def execution_authorized(self) -> bool:
        return False


def _verify_records(source, decode_state, validate_checkpoint, verify_receipt):
    """Check complete chain from an independently trusted enrollment anchor.

    Git ancestry and the origin of that anchor are the source-verifier's job.
    """
    b = source.binding
    own_paths = {p for p in source.tree.entries if p.startswith(b.prefix)}
    if own_paths != set(source.records):
        raise PRStateHold("INCOMPLETE_RECORD_INVENTORY")
    previous = source.initial_record_sha256
    revision = source.initial_revision
    last = None
    for path, raw in sorted(source.records.items()):
        revision += 1
        if path != b.prefix + f"r{revision:016d}.json":
            raise PRStateHold("RECORD_REVISION_GAP")
        digest = sha256(raw).hexdigest()
        if source.tree.entries[path] != TreeEntry("100644", digest):
            raise PRStateHold("RECORD_TREE_MISMATCH")
        try:
            record = json.loads(raw)
            if not isinstance(record, dict) or set(record) != {
                "schema_version", "repository", "pr_number", "branch", "work_id", "revision",
                "expected_parent", "previous_record_sha256", "state_body", "state_body_sha256",
            }:
                raise PRStateHold("INVALID_RECORD_SCHEMA")
            canonical = (json.dumps(record, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
            body = record["state_body"]
            if (raw != canonical or type(record["schema_version"]) is not int
                    or record["schema_version"] != 1 or record["repository"] != b.repository
                    or type(record["pr_number"]) is not int or record["pr_number"] != b.pr_number
                    or record["branch"] != b.branch or record["work_id"] != b.work_id
                    or type(record["revision"]) is not int or record["revision"] != revision
                    or record["previous_record_sha256"] != previous
                    or not _valid(record["expected_parent"], _SHA)
                    or not isinstance(body, str) or len(body.encode("utf-8")) > 240_000
                    or not body.startswith("<!-- samuel-controller-state -->\n")
                    or sha256(body.encode("utf-8")).hexdigest() != record["state_body_sha256"]):
                raise PRStateHold("RECORD_CHAIN_OR_IDENTITY_MISMATCH")
            last = decode_state(body)
            if last.research_id != b.work_id or type(last.revision) is not int or last.revision != revision:
                raise PRStateHold("DECODED_STATE_MISMATCH")
        except PRStateHold:
            raise
        except Exception as exc:
            raise PRStateHold("RECORD_DECODE_FAILED") from exc
        previous = digest
    try:
        cp = validate_checkpoint(last.progress_checkpoint)
        if (cp["work_id"] != b.work_id or cp["plan_sha256"] != source.plan_sha256
                or cp["policy_sha256"] != source.policy_sha256):
            raise PRStateHold("CHECKPOINT_SCOPE_MISMATCH")
        required = {u.unit_id: u.input_sha256 for u in source.required_units}
        actual = {u["id"]: u["input_sha256"] for u in cp["units"]}
        if actual != required:
            raise PRStateHold("WORK_COVERAGE_MISMATCH")
        for index, unit in enumerate(cp["units"]):
            receipt = cp["receipts"].get(str(index))
            if not isinstance(receipt, dict) or receipt.get("outcome") not in {"PASS", "NOOP"}:
                raise PRStateHold("WORK_UNIT_INCOMPLETE")
            if verify_receipt(source, unit["id"], receipt) is not True:
                raise PRStateHold("SOURCE_RECEIPT_UNVERIFIED")
    except PRStateHold:
        raise
    except Exception as exc:
        raise PRStateHold("CHECKPOINT_OR_RECEIPT_INVALID") from exc
    return len(source.records), len(required)


def reconcile_merge(*, base: TreeSnapshot, sources: tuple[PRMergeSource, ...],
                    candidate: TreeSnapshot, gate_evidence: tuple[GateEvidence, ...],
                    expected_sources: tuple[tuple[PRBinding, str], ...],
                    decode_state: Callable, validate_checkpoint: Callable,
                    verify_tree: Callable, verify_inventory: Callable, verify_source: Callable, verify_receipt: Callable,
                    verify_gate: Callable, required_gates: tuple[str, ...] = ()) -> MergeReconciliation:
    """Return evidence review eligibility, never authorization.

    verify_tree(snapshot) authenticates the exact complete tree (including
    modes, symlink targets and submodule refs). verify_inventory(base, expected_sources)
    authenticates the independently enrolled full PR/head inventory. verify_source(base, source)
    authenticates PR identity, common base, enrollment/plan, full chain history
    and source HEAD; verify_receipt authenticates each unit proof at that HEAD.
    verify_gate(base, sources, candidate, evidence) authenticates independent
    semantic and validation evidence for the *integrated* candidate and source
    set. These runtime ports are not implemented by this pure adapter.
    """
    heads = tuple(s.tree.head for s in sources if isinstance(s, PRMergeSource)) if isinstance(sources, tuple) else ()
    head = candidate.head if isinstance(candidate, TreeSnapshot) else ""
    records = units = 0

    def result(status, *reasons):
        return MergeReconciliation(status, tuple(reasons), heads, head, records, units)

    try:
        if (not isinstance(base, TreeSnapshot) or not isinstance(candidate, TreeSnapshot)
                or not isinstance(sources, tuple) or not 1 <= len(sources) <= 100
                or len(heads) != len(sources) or len(set(heads)) != len(heads)
                or not all(callable(f) for f in (decode_state, validate_checkpoint, verify_tree,
                                                 verify_inventory, verify_source, verify_receipt, verify_gate))
                or not isinstance(required_gates, tuple)
                or any(not isinstance(g, str) or not g.strip() for g in required_gates)):
            return result("HOLD", "INVALID_RECONCILIATION_INPUT")
        if (not isinstance(expected_sources, tuple)
                or any(not isinstance(x, tuple) or len(x) != 2
                       or not isinstance(x[0], PRBinding) or not _valid(x[1], _SHA)
                       for x in expected_sources)
                or len(expected_sources) != len(sources)
                or set(expected_sources) != {(s.binding, s.tree.head) for s in sources}
                or verify_inventory(base, expected_sources) is not True):
            return result("HOLD", "SOURCE_INVENTORY_MISMATCH")
        bindings = validate_bindings(s.binding for s in sources)
        if len({b.repository.lower() for b in bindings}) != 1:
            return result("HOLD", "CROSS_REPOSITORY_MERGE")
        if len({b.work_id for b in bindings}) != len(bindings):
            return result("HOLD", "SAME_WORK_RECONCILIATION_REQUIRED")
        if any(s.base_head != base.head or s.tree.head == base.head for s in sources):
            return result("HOLD", "COMMON_BASE_REQUIRED")
        if not all(verify_tree(t) is True for t in (base, candidate, *(s.tree for s in sources))):
            return result("HOLD", "TREE_EVIDENCE_UNVERIFIED")
        changes = {}
        for source in sources:
            if verify_source(base, source) is not True:
                return result("HOLD", "SOURCE_EVIDENCE_UNVERIFIED")
            if any(p.startswith(source.binding.prefix) for p in base.entries):
                return result("HOLD", "SOURCE_NAMESPACE_ALREADY_ARCHIVED")
            n, m = _verify_records(source, decode_state, validate_checkpoint, verify_receipt)
            records += n
            units += m
            for path in sorted(set(base.entries) | set(source.tree.entries)):
                before, after = base.entries.get(path), source.tree.entries.get(path)
                if before == after:
                    continue
                if path.startswith(_STATE_ROOT) and (before is not None or path not in source.records):
                    return result("HOLD", "FOREIGN_OR_HISTORICAL_STATE_MUTATION:" + path)
                if path in changes and changes[path] != after:
                    return result("HOLD", "DIVERGENT_PATH_CHANGE:" + path)
                changes[path] = after
        expected = dict(base.entries)
        for path, entry in changes.items():
            if entry is None:
                expected.pop(path, None)
            else:
                expected[path] = entry
        differences = sorted(p for p in set(expected) | set(candidate.entries)
                             if expected.get(p) != candidate.entries.get(p))
        if differences:
            return result("HOLD", *("CANDIDATE_TREE_MISMATCH:" + p for p in differences[:20]))
        if not isinstance(gate_evidence, tuple) or any(not isinstance(g, GateEvidence) for g in gate_evidence):
            return result("HOLD", "INVALID_GATE_EVIDENCE")
        gates = _REQUIRED_GATES | set(required_gates)
        if len({g.gate for g in gate_evidence}) != len(gate_evidence) or {g.gate for g in gate_evidence} != gates:
            return result("HOLD", "INTEGRATION_GATE_INVENTORY_MISMATCH")
        for evidence in gate_evidence:
            if (evidence.candidate_head != candidate.head or evidence.outcome != "PASS"
                    or not isinstance(evidence.evidence_ref, str) or not evidence.evidence_ref.strip()
                    or verify_gate(base, sources, candidate, evidence) is not True):
                return result("HOLD", "INTEGRATION_GATE_UNVERIFIED:" + evidence.gate)
        return result("READY_FOR_REVIEW")
    except PRStateHold as exc:
        return result("HOLD", str(exc))
    except Exception:
        return result("HOLD", "RECONCILIATION_EVIDENCE_UNAVAILABLE")
