"""Plan post-change verification obligations from observed graph differences.

A change plan never approves mutation or proves behavioral compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..analysis.diff import GraphDiff, compare_graphs
from ..diagnostics.receipt import EvidenceReceipt
from ..graph import GraphSnapshot
from .consistency import verify_generated_artifact


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


__all__ = ["ChangeVerificationPlan", "plan_change_verification"]
