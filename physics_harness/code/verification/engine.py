"""Evidence-first verification of generated source artifacts and graph changes.

No fixed directory layout, package allowlist or policy-based architecture gate.
VERIFIED covers provenance and bounded source-snapshot consistency only.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..analysis.diff import GraphDiff, compare_graphs
from ..diagnostics.receipt import EvidenceReceipt
from ..graph import GraphSnapshot


@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    repository: str
    revision: str
    scope_id: str
    status: str
    verified_properties: tuple[str, ...]
    unverified_properties: tuple[str, ...]
    failures: tuple[str, ...]

    @property
    def artifact_verified(self) -> bool:
        return self.status == "VERIFIED"

    @property
    def semantic_compatibility_proven(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class ChangeVerificationPlan:
    before_revision: str
    after_revision: str
    change: GraphDiff
    required_checks: tuple[str, ...]
    impacted_subjects: tuple[str, ...]
    findings: tuple[str, ...]
    disposition: str

    @property
    def mutation_approved(self) -> bool:
        # Source graph comparison cannot itself approve a repository edit.
        return False


def verify_generated_artifact(
    graph: GraphSnapshot, receipt: EvidenceReceipt,
) -> VerificationReceipt:
    """Check actual diagnostic output against exact-HEAD source receipts.

    Does not re-read Git objects or assert that source syntax was interpreted
    exhaustively. A matching Blob SHA is provenance metadata, not execution.
    """
    if not isinstance(graph, GraphSnapshot) or not isinstance(
        receipt, EvidenceReceipt
    ):
        raise TypeError("verification requires GraphSnapshot and EvidenceReceipt")

    scope = graph.scope
    failures: set[str] = set()
    unknown: set[str] = set()
    verified: set[str] = {"GRAPH_REFERENCE_INTEGRITY"}

    if (scope.id != receipt.scope_id or scope.repository != receipt.repository
            or scope.revision != receipt.revision):
        failures.add("GRAPH_RECEIPT_SCOPE_MISMATCH")
    else:
        verified.add("SCOPE_IDENTITY")

    paths = {item.path: item for item in receipt.files}
    included = tuple(sorted(
        item.path for item in receipt.files if item.status != "EXCLUDED"
    ))
    excluded = tuple(sorted(
        item.path for item in receipt.files if item.status == "EXCLUDED"
    ))
    if scope.included_paths != included or scope.excluded_paths != excluded:
        failures.add("GRAPH_RECEIPT_FILES_MISMATCH")
    else:
        verified.add("FILE_SCOPE_MEMBERSHIP")

    if (scope.completeness != receipt.completeness
            or scope.unresolved != receipt.unresolved):
        failures.add("GRAPH_RECEIPT_COMPLETENESS_MISMATCH")
    elif scope.completeness != "COMPLETE":
        unknown.add("INCOMPLETE_REQUESTED_SCOPE")
    else:
        verified.add("REQUESTED_FILE_COVERAGE")

    if any(item.status != "SCANNED" for item in receipt.files
           if item.status != "EXCLUDED"):
        unknown.add("UNSCANNED_REQUESTED_FILES")
    if not included:
        unknown.add("EMPTY_SOURCE_SCOPE")

    for evidence in graph.evidence:
        attrs = evidence.attributes
        if evidence.observation_status == "RUNTIME_OBSERVED":
            if attrs.get("source_sha") != scope.revision:
                failures.add("CROSS_HEAD_RUNTIME_EVIDENCE:" + evidence.id)
            if not all(attrs.get(key) for key in ("run_id", "attempt", "url")):
                failures.add("RUNTIME_PROVENANCE_INCOMPLETE:" + evidence.id)
            if attrs.get("url") != evidence.source_ref:
                failures.add("RUNTIME_SOURCE_REFERENCE_MISMATCH:" + evidence.id)
            unknown.add("RUNTIME_EXECUTION_NOT_INDEPENDENTLY_VERIFIED")
            continue

        ref = evidence.source_ref
        matches = []
        for path, item in paths.items():
            if ref == path + "@" + item.blob_sha:
                matches.append((path, item, None))
            elif ref.startswith(path + ":") and ref.endswith("@" + item.blob_sha):
                line = ref[len(path) + 1:-(len(item.blob_sha) + 1)]
                if line.isdecimal() and int(line) > 0:
                    matches.append((path, item, int(line)))
        if len(matches) != 1:
            failures.add("SOURCE_REFERENCE_NOT_BOUND_TO_RECEIPT:" + evidence.id)
            continue

        path, file, line = matches[0]
        if file.status == "EXCLUDED":
            failures.add("SOURCE_EVIDENCE_FROM_EXCLUDED_PATH:" + evidence.id)
        if attrs.get("blob_sha") != file.blob_sha:
            failures.add("SOURCE_BLOB_MISMATCH:" + evidence.id)
        revision = attrs.get("source_sha", attrs.get("revision"))
        if revision != scope.revision:
            failures.add("SOURCE_REVISION_MISMATCH:" + evidence.id)
        if attrs.get("path") not in (None, path):
            failures.add("SOURCE_PATH_MISMATCH:" + evidence.id)
        if line is not None and attrs.get("line") != line:
            failures.add("SOURCE_LINE_MISMATCH:" + evidence.id)
        if evidence.method != "GIT_TREE" and line is None:
            failures.add("SOURCE_LINE_ABSENT:" + evidence.id)
        if evidence.observation_status == "UNRESOLVED":
            unknown.add("UNRESOLVED_SOURCE_EVIDENCE")

    if not any(x.startswith("SOURCE_") for x in failures):
        verified.add("SOURCE_METADATA_PROVENANCE")

    # Verified source integrity must not be conflated with global safety.
    unknown.update((
        "GLOBAL_CONSUMER_CLOSURE_UNPROVEN",
        "SEMANTIC_COMPATIBILITY_UNPROVEN",
        "NATIVE_RUNTIME_COMPATIBILITY_UNPROVEN",
    ))
    status = "FAILED" if failures else (
        "UNVERIFIED" if scope.completeness != "COMPLETE" or
        "UNSCANNED_REQUESTED_FILES" in unknown or
        "UNRESOLVED_SOURCE_EVIDENCE" in unknown or
        "RUNTIME_EXECUTION_NOT_INDEPENDENTLY_VERIFIED" in unknown or
        "EMPTY_SOURCE_SCOPE" in unknown else "VERIFIED"
    )
    return VerificationReceipt(
        repository=scope.repository, revision=scope.revision,
        scope_id=scope.id, status=status,
        verified_properties=tuple(sorted(verified)),
        unverified_properties=tuple(sorted(unknown)),
        failures=tuple(sorted(failures)),
    )


def plan_change_verification(
    before: GraphSnapshot, after: GraphSnapshot,
    before_receipt: EvidenceReceipt, after_receipt: EvidenceReceipt,
) -> ChangeVerificationPlan:
    """Derive work from observed structural changes, not naming policies."""
    first = verify_generated_artifact(before, before_receipt)
    second = verify_generated_artifact(after, after_receipt)
    diff = compare_graphs(before, after)
    findings = set(first.failures + second.failures)
    checks: set[str] = set()
    subjects = set(
        diff.added_nodes + diff.removed_nodes + diff.changed_nodes
        + diff.added_edges + diff.removed_edges + diff.changed_edges
    )

    if first.status != "VERIFIED" or second.status != "VERIFIED":
        checks.add("RESOLVE_SOURCE_PROVENANCE_AND_COVERAGE")
    if diff.removed_nodes or diff.removed_edges:
        checks.add("VERIFY_REMOVED_CONSUMERS_AND_REFERENCES")
    if diff.added_nodes or diff.changed_nodes:
        checks.add("VERIFY_CHANGED_DECLARATIONS_AND_INTERFACES")
    if diff.added_edges or diff.changed_edges or diff.removed_edges:
        checks.add("VERIFY_DEPENDENCY_AND_CALL_IMPACT")
    if any(
        edge.relation.endswith("_CANDIDATE")
        for edge in after.edges if edge.id in set(diff.added_edges + diff.changed_edges)
    ):
        checks.add("RESOLVE_CANDIDATE_DEPENDENCIES")
    if diff.coverage_changed or diff.new_unresolved:
        checks.add("VERIFY_SCOPE_AND_UNRESOLVED_DELTA")
    if (diff.added_evidence or diff.removed_evidence or diff.changed_evidence
            or subjects):
        checks.add("REPLAY_IMPACTED_TESTS_AT_AFTER_HEAD")
    if checks:
        checks.add("VERIFY_BEHAVIORAL_COMPATIBILITY")
    if first.repository != second.repository:
        findings.add("CROSS_REPOSITORY_CHANGE")
    return ChangeVerificationPlan(
        before_revision=first.revision, after_revision=second.revision,
        change=diff, required_checks=tuple(sorted(checks)),
        impacted_subjects=tuple(sorted(subjects)),
        findings=tuple(sorted(findings)),
        disposition="BLOCKED" if findings else (
            "UNVERIFIED" if checks else "VERIFIED_SOURCE_ONLY"
        ),
    )


__all__ = [
    "VerificationReceipt", "ChangeVerificationPlan",
    "verify_generated_artifact", "plan_change_verification",
]
