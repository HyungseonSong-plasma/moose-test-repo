"""Evidence-bound, strategy-neutral refactor planning contracts.

Planning does not evaluate HU, prescribe a transformation, execute edits,
verify semantic compatibility, or authorize mutation. It evaluates alternatives
against source evidence and independently supplied constraint checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..analysis.result import AnalysisRecord as PlanningAssessment

if TYPE_CHECKING:
    from ..diagnostics.assemble import DiagnosticResult


@dataclass(frozen=True, slots=True)
class HardConstraint:
    id: str
    description: str

    def __post_init__(self) -> None:
        _nonempty(self.id, "constraint.id")
        _nonempty(self.description, "constraint.description")


@dataclass(frozen=True, slots=True)
class PlanningContext:
    """Immutable read-only projection of a single exact-source Graph target."""

    repository: str
    revision: str
    scope_id: str
    target_id: str
    target_name: str
    source_path: str | None
    source_blob_sha: str | None
    source_status: str
    provenance_status: str
    structural_metrics: tuple[tuple[str, int], ...]
    available_paths: tuple[str, ...]
    evidence_ids: tuple[str, ...]  # All evidence IDs in scanned scope
    target_evidence_ids: tuple[str, ...]  # Target + incident-edge evidence
    candidate_relations: tuple[str, ...]  # Explicitly NOT resolved dependencies
    assessments: tuple[PlanningAssessment, ...]
    objectives: tuple[str, ...]
    hard_constraints: tuple[HardConstraint, ...]
    unknowns: tuple[str, ...]

    @property
    def mutation_approved(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class PlanningAlternative:
    """A proposed change or KEEP baseline, without self-certified check results."""

    id: str
    action: str  # KEEP or CHANGE, deliberately no built-in strategy catalogue
    description: str
    affected_paths: tuple[str, ...] = ()  # existing sources to inspect/change
    created_paths: tuple[str, ...] = ()  # proposed destinations absent from scan
    removed_paths: tuple[str, ...] = ()  # proposed removals of existing sources
    evidence_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    expected_benefits: tuple[str, ...] = ()
    costs: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    required_checks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.id, "alternative.id")
        if self.action not in {"KEEP", "CHANGE"}:
            raise ValueError("INVALID_ALTERNATIVE_ACTION")
        _nonempty(self.description, "alternative.description")
        for name in ("affected_paths", "created_paths", "removed_paths",
                     "evidence_ids", "assumptions",
                     "expected_benefits", "costs", "risks", "required_checks"):
            _strings(getattr(self, name), f"alternative.{name}")
        from ..diagnostics.request import normalized_path
        for path in self.affected_paths + self.created_paths + self.removed_paths:
            normalized_path(path)
        if set(self.created_paths) & (set(self.affected_paths) | set(self.removed_paths)):
            raise ValueError("CREATED_PATH_OVERLAPS_EXISTING_PATH")


@dataclass(frozen=True, slots=True)
class ConstraintCheck:
    """Verification result, supplied separately from the proposed change.

    The caller must tie these checks to real verification evidence. A textual
    check_ref is not an authentication mechanism; consumers must validate the
    referenced verifier output before treating PASS as established.
    """

    constraint_id: str
    alternative_id: str
    baseline_revision: str
    status: str  # PASS / FAIL / UNVERIFIED
    check_ref: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.constraint_id, "check.constraint_id")
        _nonempty(self.alternative_id, "check.alternative_id")
        _nonempty(self.baseline_revision, "check.baseline_revision")
        if self.status not in {"PASS", "FAIL", "UNVERIFIED"}:
            raise ValueError("INVALID_CHECK_STATUS")
        _nonempty(self.check_ref, "check.check_ref")
        _strings(self.evidence_ids, "check.evidence_ids")


@dataclass(frozen=True, slots=True)
class PlanValidation:
    alternative_id: str
    disposition: str  # ADMISSIBLE / HOLD / BLOCKED, not an edit authorization
    blockers: tuple[str, ...]
    unknowns: tuple[str, ...]
    required_checks: tuple[str, ...]

    @property
    def mutation_approved(self) -> bool:
        return False


def build_planning_context(
    diagnostic: DiagnosticResult,
    target_id: str,
    *,
    objectives: tuple[str, ...] = (),
    hard_constraints: tuple[HardConstraint, ...] = (),
    assessments: tuple[PlanningAssessment, ...] = (),
) -> PlanningContext:
    """Project actual run_scan output into source-bound planning facts.

    Graph-only AST counts are *structural measurements*, not HU scores.
    Target selection happens after scanning: run_scan roots are unsupported.
    """
    _strings(objectives, "objectives")
    _typed_tuple(hard_constraints, HardConstraint, "hard_constraints")
    _typed_tuple(assessments, PlanningAssessment, "assessments")
    _unique((c.id for c in hard_constraints), "DUPLICATE_CONSTRAINT_ID")
    _unique((a.name for a in assessments), "DUPLICATE_ASSESSMENT_NAME")

    graph, receipt, verification = (
        diagnostic.graph, diagnostic.receipt, diagnostic.verification
    )
    scope = graph.scope
    if (scope.repository != receipt.repository or scope.revision != receipt.revision
            or scope.id != receipt.scope_id):
        raise ValueError("PLANNING_SCOPE_RECEIPT_MISMATCH")
    if verification is not None and (
        verification.repository != scope.repository
        or verification.revision != scope.revision
        or verification.scope_id != scope.id
    ):
        raise ValueError("PLANNING_VERIFICATION_SCOPE_MISMATCH")

    nodes = graph.nodes_by_id()
    if target_id not in nodes:
        raise ValueError("UNKNOWN_PLANNING_TARGET")
    target = nodes[target_id]
    evidence_by_id = graph.evidence_by_id()
    for assessment in assessments:
        references = set(assessment.evidence_ids)
        for value in assessment.values:
            references.update(value.evidence_ids)
        if references - evidence_by_id.keys():
            raise ValueError("UNKNOWN_ASSESSMENT_EVIDENCE")
        if assessment.source_revision is not None and assessment.source_revision != scope.revision:
            raise ValueError("ASSESSMENT_SOURCE_REVISION_MISMATCH")

    files = {entry.path: entry for entry in receipt.files}
    path = target.location.path if target.location else None
    record = files.get(path) if path else None
    target_evidence = set(target.evidence_ids)
    relations = set()
    for edge in graph.edges:
        if edge.source_id == target_id or edge.target_id == target_id:
            target_evidence.update(edge.evidence_ids)
            if edge.relation.endswith("_CANDIDATE"):
                relations.add(edge.relation)

    unknowns = set(scope.unresolved) | set(receipt.unresolved)
    if scope.completeness != "COMPLETE" or receipt.completeness != "COMPLETE":
        unknowns.add("INCOMPLETE_PLANNING_SCOPE")
    for assessment in assessments:
        unknowns.update(assessment.unknowns)
    if not path or record is None:
        unknowns.add("TARGET_SOURCE_NOT_IN_RECEIPT")
    elif record.status != "SCANNED":
        unknowns.add(f"TARGET_SOURCE_NOT_SCANNED:{record.status}")
    if verification is None:
        unknowns.add("SOURCE_ARTIFACT_VERIFICATION_MISSING")
    else:
        if verification.status not in {"VERIFIED", "UNVERIFIED", "FAILED"}:
            raise ValueError("INVALID_PLANNING_VERIFICATION_STATUS")
        if verification.status != "VERIFIED":
            unknowns.add(f"SOURCE_ARTIFACT_{verification.status}")
        # These are disclosed, not automatically assumed to block planning:
        # a source-only VERIFIED result still lacks semantic/runtime proof.
        unknowns.update(verification.unverified_properties)

    metrics = []
    for key in ("loc", "branches", "max_branch_nesting"):
        value = target.attributes.get(key)
        if type(value) is int and value >= 0:
            metrics.append((key, value))

    return PlanningContext(
        repository=scope.repository, revision=scope.revision,
        scope_id=scope.id, target_id=target_id,
        target_name=target.qualified_name or target.name,
        source_path=path, source_blob_sha=record.blob_sha if record else None,
        source_status=record.status if record else "UNVERIFIED",
        provenance_status=verification.status if verification else "UNVERIFIED",
        structural_metrics=tuple(metrics),
        available_paths=tuple(sorted(
            p for p, f in files.items() if f.status == "SCANNED"
        )),
        evidence_ids=tuple(sorted(evidence_by_id)),
        target_evidence_ids=tuple(sorted(target_evidence)),
        candidate_relations=tuple(sorted(relations)),
        assessments=assessments, objectives=objectives,
        hard_constraints=hard_constraints, unknowns=tuple(sorted(unknowns)),
    )


def validate_alternative(
    context: PlanningContext,
    alternative: PlanningAlternative,
    *,
    constraint_checks: tuple[ConstraintCheck, ...] = (),
) -> PlanValidation:
    """Validate source references and externally verified constraint checks.

    ADMISSIBLE means structurally eligible for consideration, not safe to
    edit or proven to improve HU. Future checks and behavior verification remain obligations.
    """
    if not isinstance(context, PlanningContext):
        raise TypeError("PLANNING_CONTEXT_REQUIRED")
    if not isinstance(alternative, PlanningAlternative):
        raise TypeError("PLANNING_ALTERNATIVE_REQUIRED")
    _typed_tuple(constraint_checks, ConstraintCheck, "constraint_checks")
    _unique((c.constraint_id for c in constraint_checks), "DUPLICATE_CONSTRAINT_CHECK")
    declared = {c.id for c in context.hard_constraints}
    known_evidence = set(context.evidence_ids)
    target_evidence = set(context.target_evidence_ids)
    blocked: set[str] = set()
    unknown: set[str] = set()
    required = set(alternative.required_checks)

    if context.provenance_status == "FAILED":
        blocked.add("SOURCE_PROVENANCE_FAILED")
    elif context.provenance_status != "VERIFIED" or context.source_status != "SCANNED":
        unknown.add("SOURCE_PROVENANCE_UNVERIFIED")

    if alternative.action == "KEEP":
        if (alternative.affected_paths or alternative.created_paths
                or alternative.removed_paths or alternative.required_checks):
            blocked.add("KEEP_MUST_NOT_DECLARE_CHANGES")
    else:
        required.update(("REPLAY_IMPACTED_TESTS_AT_AFTER_HEAD",
                         "VERIFY_BEHAVIORAL_COMPATIBILITY",
                         "VERIFY_POST_CHANGE_GRAPH_DIFF"))
        if not context.objectives:
            unknown.add("IMPROVEMENT_OBJECTIVE_UNDECLARED")
        if not alternative.expected_benefits:
            unknown.add("EXPECTED_BENEFIT_UNDECLARED")
        if not alternative.risks:
            unknown.add("RISK_ASSESSMENT_MISSING")
        if not (alternative.affected_paths or alternative.created_paths):
            unknown.add("AFFECTED_PATHS_UNDECLARED")
        if alternative.created_paths:
            required.update(("VERIFY_PROPOSED_NEW_PATHS_AT_BASELINE",
                             "VERIFY_NEW_PATHS_AT_AFTER_HEAD"))
            for path in alternative.created_paths:
                if path in context.available_paths:
                    blocked.add(f"PROPOSED_NEW_PATH_ALREADY_SCANNED:{path}")
        if alternative.removed_paths:
            required.add("VERIFY_REMOVED_CONSUMERS_AND_REFERENCES")
            for path in alternative.removed_paths:
                if path not in context.available_paths:
                    unknown.add(f"REMOVED_PATH_OUTSIDE_VERIFIED_SOURCE_SCOPE:{path}")
                if path not in alternative.affected_paths:
                    unknown.add(f"REMOVED_PATH_NOT_DECLARED_AFFECTED:{path}")
        if not set(alternative.evidence_ids) & target_evidence:
            unknown.add("TARGET_EVIDENCE_NOT_CITED")
        for path in alternative.affected_paths:
            if path not in context.available_paths:
                unknown.add(f"PATH_OUTSIDE_VERIFIED_SOURCE_SCOPE:{path}")

    checks = {c.constraint_id: c for c in constraint_checks}
    for check in constraint_checks:
        if check.alternative_id != alternative.id:
            blocked.add(f"CHECK_FOR_ANOTHER_ALTERNATIVE:{check.constraint_id}")
        if check.baseline_revision != context.revision:
            blocked.add(f"CHECK_FOR_ANOTHER_REVISION:{check.constraint_id}")
        if check.constraint_id not in declared:
            blocked.add(f"UNDECLARED_CONSTRAINT_CHECK:{check.constraint_id}")
        if set(check.evidence_ids) - known_evidence:
            blocked.add(f"UNKNOWN_CHECK_EVIDENCE:{check.constraint_id}")
    # KEEP is not a proposed mutation: preservation obligations are not
    # generated for unchanged code. Explicitly supplied failing checks are
    # still reported; a baseline finding must not be hidden.
    for cid in sorted(declared):
        check = checks.get(cid)
        if check is None:
            if alternative.action != "KEEP":
                required.add(f"CHECK_CONSTRAINT:{cid}")
                unknown.add(f"CONSTRAINT_NOT_EVALUATED:{cid}")
        elif check.status == "FAIL":
            blocked.add(f"CONSTRAINT_FAILED:{cid}")
        elif check.status == "UNVERIFIED":
            if alternative.action != "KEEP":
                required.add(f"CHECK_CONSTRAINT:{cid}")
                unknown.add(f"CONSTRAINT_UNVERIFIED:{cid}")

    if set(alternative.evidence_ids) - known_evidence:
        blocked.add("UNKNOWN_ALTERNATIVE_EVIDENCE")
    if blocked:
        disposition = "BLOCKED"
    elif unknown:
        disposition = "HOLD"
    else:
        disposition = "ADMISSIBLE"
    return PlanValidation(
        alternative_id=alternative.id, disposition=disposition,
        blockers=tuple(sorted(blocked)),
        # Preserve all upstream limitations even when they do not prevent
        # reviewing a proposed plan. ADMISSIBLE is not a proof of behavior.
        unknowns=tuple(sorted(set(context.unknowns) | unknown)),
        required_checks=tuple(sorted(required)),
    )


def _nonempty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")


def _strings(items: tuple[str, ...], field: str) -> None:
    if not isinstance(items, tuple) or any(not isinstance(i, str) or not i.strip() for i in items):
        raise TypeError(f"{field} must be a tuple of nonempty strings")
    _unique(items, f"DUPLICATE_{field.upper().replace('.', '_')}")


def _typed_tuple(items: tuple, expected: type, field: str) -> None:
    if not isinstance(items, tuple) or any(not isinstance(i, expected) for i in items):
        raise TypeError(f"{field} must be a tuple of {expected.__name__}")


def _unique(values, error: str) -> None:
    values = list(values)
    if len(values) != len(set(values)):
        raise ValueError(error)


__all__ = [
    "HardConstraint", "PlanningAssessment", "PlanningContext",
    "PlanningAlternative", "ConstraintCheck", "PlanValidation",
    "build_planning_context", "validate_alternative",
]
