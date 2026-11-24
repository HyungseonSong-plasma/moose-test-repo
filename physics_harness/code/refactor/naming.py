"""Evidence-bound naming/extraction options; no mutation or semantic self-certification.

This policy layer deliberately consumes externally established responsibility
claims instead of inferring meaning from tokens or assuming a rename is useful.
It maps a candidate to existing strategy-neutral PlanningAlternative only after
review; both representations explicitly prohibit mutation authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re


_KINDS = frozenset({"FOLDER", "FILE", "CLASS", "FUNCTION"})
_NAME_FIT = frozenset({"VALID", "NARROW", "MISLEADING", "UNKNOWN"})
_COHERENCE = frozenset({"COHERENT", "MIXED", "UNKNOWN"})
_VARIANTS = frozenset({"KEEP", "RENAME", "EXTRACT_KEEP", "EXTRACT_RENAME", "HOLD"})
_EVIDENCE_KINDS = frozenset({"RESPONSIBILITY", "BOUNDARY", "EVOLUTION", "NAME_MISMATCH", "EXTRACTION_SEAM", "CONSUMER", "CONTEXT"})


def _nonempty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"INVALID_{field}")


def _names(items: tuple[str, ...], field: str) -> None:
    if not isinstance(items, tuple) or any(not isinstance(v, str) or not v.strip() for v in items):
        raise ValueError(f"INVALID_{field}")
    if len(set(items)) != len(items):
        raise ValueError(f"DUPLICATE_{field}")


@dataclass(frozen=True, slots=True)
class NamingEvidence:
    """A declared provenance link, NOT a verified semantic or behavioral claim."""

    id: str
    kind: str
    statement: str
    source_refs: tuple[str, ...]  # exact path:line@blob; caller must validate bytes
    source_revision: str  # before/after commit anchoring this observation

    def __post_init__(self) -> None:
        _nonempty(self.id, "EVIDENCE_ID")
        if self.kind not in _EVIDENCE_KINDS:
            raise ValueError("INVALID_EVIDENCE_KIND")
        _nonempty(self.statement, "EVIDENCE_STATEMENT")
        _names(self.source_refs, "SOURCE_REFS")
        if not self.source_refs:
            raise ValueError("EVIDENCE_PROVENANCE_REQUIRED")
        if not re.fullmatch(r"[0-9a-f]{40}", self.source_revision):
            raise ValueError("EVIDENCE_SOURCE_REVISION_REQUIRED")
        for ref in self.source_refs:
            match = re.fullmatch(r"(.+):([1-9][0-9]*)@([0-9a-f]{40})", ref)
            if not match:
                raise ValueError("INVALID_BLOB_BOUND_SOURCE_REF")
            source_path = PurePosixPath(match.group(1))
            if source_path.is_absolute() or ".." in source_path.parts:
                raise ValueError("INVALID_SOURCE_REF_PATH")


@dataclass(frozen=True, slots=True)
class NamingCase:
    """Stable name-evaluation snapshot; name fit is an *assessment*, not proof."""

    repository: str
    revision: str
    target_kind: str
    target_id: str
    current_name: str
    current_path: str
    responsibility_ids: tuple[str, ...]
    evidence: tuple[NamingEvidence, ...]
    identity_status: str  # RESOLVED / UNKNOWN
    coherence: str  # COHERENT / MIXED / UNKNOWN
    name_fit: str  # VALID / NARROW / MISLEADING / UNKNOWN
    name_mismatch_evidence_ids: tuple[str, ...] = ()
    occupied_names: tuple[str, ...] = ()  # names in the *same namespace* only
    unknowns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for attr in ("repository", "revision", "target_id", "current_name", "current_path"):
            _nonempty(getattr(self, attr), attr.upper())
        if not re.fullmatch(r"[0-9a-f]{40}", self.revision):
            raise ValueError("INVALID_REVISION")
        if self.target_kind not in _KINDS:
            raise ValueError("INVALID_TARGET_KIND")
        if self.identity_status not in {"RESOLVED", "UNKNOWN"}:
            raise ValueError("INVALID_IDENTITY_STATUS")
        if self.coherence not in _COHERENCE:
            raise ValueError("INVALID_COHERENCE")
        if self.name_fit not in _NAME_FIT:
            raise ValueError("INVALID_NAME_FIT")
        for name in ("responsibility_ids", "name_mismatch_evidence_ids", "occupied_names", "unknowns"):
            _names(getattr(self, name), name.upper())
        if not self.responsibility_ids:
            raise ValueError("CURRENT_RESPONSIBILITIES_REQUIRED")
        if not isinstance(self.evidence, tuple) or any(not isinstance(e, NamingEvidence) for e in self.evidence):
            raise TypeError("INVALID_EVIDENCE_INVENTORY")
        _names(tuple(e.id for e in self.evidence), "EVIDENCE_IDS")
        refs = {e.id: e for e in self.evidence}
        for responsibility in self.responsibility_ids:
            if not any(e.kind == "RESPONSIBILITY" and e.id == responsibility for e in self.evidence):
                raise ValueError("RESPONSIBILITY_WITHOUT_EVIDENCE:" + responsibility)
        if any(ref not in refs or refs[ref].kind != "NAME_MISMATCH"
               for ref in self.name_mismatch_evidence_ids):
            raise ValueError("INVALID_MISMATCH_EVIDENCE")
        if self.name_fit in {"NARROW", "MISLEADING"} and not self.name_mismatch_evidence_ids:
            raise ValueError("MISMATCH_CLAIM_WITHOUT_EVIDENCE")
        if self.name_fit == "VALID" and self.name_mismatch_evidence_ids:
            raise ValueError("CONTRADICTORY_NAME_ASSESSMENT")
        if self.current_name in self.occupied_names:
            raise ValueError("CURRENT_NAME_COLLISION")
        if PurePosixPath(self.current_path).is_absolute() or ".." in PurePosixPath(self.current_path).parts:
            raise ValueError("INVALID_TARGET_PATH")


@dataclass(frozen=True, slots=True)
class ExtractionUnit:
    """Implementation moved/delegated to an existing or new owner.

    A common orchestrating responsibility may remain with the original owner,
    so before/after responsibility allocation is a *cover*, not a partition.
    """

    owner_id: str
    proposed_name: str
    responsibility_ids: tuple[str, ...]
    seam_evidence_ids: tuple[str, ...]
    destination_path: str | None = None
    destination_existing: bool = False

    def __post_init__(self) -> None:
        _nonempty(self.owner_id, "EXTRACTION_OWNER")
        _nonempty(self.proposed_name, "EXTRACTION_NAME")
        _names(self.responsibility_ids, "EXTRACTION_RESPONSIBILITIES")
        _names(self.seam_evidence_ids, "EXTRACTION_SEAMS")
        if not self.responsibility_ids or not self.seam_evidence_ids:
            raise ValueError("EXTRACTION_WITNESSES_REQUIRED")
        if not isinstance(self.destination_existing, bool):
            raise TypeError("INVALID_DESTINATION_EXISTENCE")
        if self.destination_existing and self.destination_path is None:
            raise ValueError("EXISTING_DESTINATION_PATH_REQUIRED")
        if self.destination_path is not None:
            _nonempty(self.destination_path, "DESTINATION_PATH")
            path = PurePosixPath(self.destination_path)
            if path.is_absolute() or ".." in path.parts or str(path) == ".":
                raise ValueError("INVALID_DESTINATION_PATH")


@dataclass(frozen=True, slots=True)
class NamingOption:
    """GPT candidate; absence of supporting evidence always fails closed."""

    id: str
    variant: str
    rationale: str
    proposed_name: str | None = None
    coverage_rationale: str = ""
    boundary_rationale: str = ""
    context_rationale: str = ""
    retained_responsibility_ids: tuple[str, ...] = ()
    extracted_units: tuple[ExtractionUnit, ...] = ()
    post_extraction_name_fit: str | None = None  # assessment, independently verified later
    evidence_ids: tuple[str, ...] = ()
    rejected_names: tuple[str, ...] = ()
    impact_paths: tuple[str, ...] = ()
    module_path_policy: str | None = None  # explicit retain vs retire, never inferred

    def __post_init__(self) -> None:
        if self.module_path_policy not in {None, "PRESERVE_COMPATIBILITY", "RETIRE_OLD_PATH"}:
            raise ValueError("INVALID_MODULE_PATH_POLICY")
        if self.module_path_policy is not None and self.variant not in {"RENAME", "EXTRACT_RENAME"}:
            raise ValueError("MODULE_PATH_POLICY_REQUIRES_RENAME")
        _nonempty(self.id, "OPTION_ID")
        if self.variant not in _VARIANTS:
            raise ValueError("INVALID_OPTION_VARIANT")
        _nonempty(self.rationale, "OPTION_RATIONALE")
        for name in ("retained_responsibility_ids", "evidence_ids", "rejected_names", "impact_paths"):
            _names(getattr(self, name), name.upper())
        if not isinstance(self.extracted_units, tuple) or any(not isinstance(e, ExtractionUnit) for e in self.extracted_units):
            raise TypeError("INVALID_EXTRACTION_UNITS")
        _names(tuple(x.owner_id for x in self.extracted_units), "EXTRACTION_OWNERS")
        if self.post_extraction_name_fit is not None and self.post_extraction_name_fit not in _NAME_FIT:
            raise ValueError("INVALID_POST_EXTRACTION_NAME_FIT")
        if self.proposed_name is not None:
            _nonempty(self.proposed_name, "PROPOSED_NAME")
        if self.variant in {"KEEP", "HOLD"} and (self.proposed_name is not None or self.extracted_units or self.impact_paths):
            raise ValueError("NO_CHANGE_OPTION_MUST_NOT_MUTATE")
        if self.variant in {"RENAME", "EXTRACT_RENAME"} and not self.proposed_name:
            raise ValueError("RENAME_REQUIRES_NEW_NAME")
        if self.variant in {"RENAME", "KEEP", "HOLD"} and self.extracted_units:
            raise ValueError("EXTRACTION_VARIANT_REQUIRED")
        if self.variant in {"EXTRACT_RENAME", "EXTRACT_KEEP"} and not self.extracted_units:
            raise ValueError("EXTRACTION_UNIT_REQUIRED")
        if self.variant == "EXTRACT_KEEP" and self.proposed_name is not None:
            raise ValueError("EXTRACT_KEEP_MUST_KEEP_NAME")
        if self.variant not in {"EXTRACT_KEEP", "EXTRACT_RENAME"} and self.post_extraction_name_fit is not None:
            raise ValueError("POST_EXTRACTION_ASSESSMENT_WITHOUT_EXTRACTION")


@dataclass(frozen=True, slots=True)
class NamingOptionReview:
    option_id: str
    disposition: str  # BASELINE / REVIEWABLE / HOLD / REJECTED
    blockers: tuple[str, ...]
    unknowns: tuple[str, ...]
    required_checks: tuple[str, ...]

    @property
    def mutation_approved(self) -> bool:
        return False


def review_naming_option(case: NamingCase, option: NamingOption) -> NamingOptionReview:
    """Check a *proposal's* completeness; never verify semantic assertions.

    Every editing option remains conditional on independent before/after
    semantic, consumer, contract and exact-revision evidence. This function
    deliberately cannot grant execution authority from GPT-declared claims.
    """
    if not isinstance(case, NamingCase) or not isinstance(option, NamingOption):
        raise TypeError("NAMING_CASE_AND_OPTION_REQUIRED")
    known = {e.id: e for e in case.evidence}
    responsibilities = set(case.responsibility_ids)
    blocked: set[str] = set()
    unknown = set(case.unknowns)
    required: set[str] = set()
    refs = set(option.evidence_ids)
    if refs - known.keys():
        blocked.add("UNKNOWN_OPTION_EVIDENCE")
    if option.variant in {"KEEP", "HOLD"}:
        if option.retained_responsibility_ids and set(option.retained_responsibility_ids) != responsibilities:
            blocked.add("UNCHANGED_RESPONSIBILITY_MISMATCH")
        if option.variant == "HOLD":
            unknown.add("DELIBERATELY_HELD")
        return NamingOptionReview(option.id,
                                  "REJECTED" if blocked else ("HOLD" if option.variant == "HOLD" else "BASELINE"),
                                  tuple(sorted(blocked)), tuple(sorted(unknown)), ())

    if not any(known[i].kind == "EVOLUTION" for i in refs if i in known):
        unknown.add("CODE_EVOLUTION_NOT_EVIDENCED")
    if case.current_path not in option.impact_paths:
        unknown.add("TARGET_NOT_IN_IMPACT_PATHS")
    if case.identity_status != "RESOLVED":
        unknown.add("LOGICAL_IDENTITY_UNRESOLVED")
    if case.name_fit == "VALID" and option.variant in {"RENAME", "EXTRACT_RENAME"}:
        blocked.add("VALID_NAME_DOES_NOT_REQUIRE_RENAME")
    if case.name_fit == "UNKNOWN" and option.variant in {"RENAME", "EXTRACT_RENAME"}:
        unknown.add("NAME_MISMATCH_UNRESOLVED")
    if case.coherence == "UNKNOWN":
        unknown.add("RESPONSIBILITY_COHERENCE_UNRESOLVED")
    if case.coherence == "MIXED" and option.variant == "RENAME":
        blocked.add("MIXED_RESPONSIBILITIES_CANNOT_BE_FIXED_BY_RENAME")
    if option.variant in {"RENAME", "EXTRACT_RENAME"}:
        if case.target_kind in {"FILE", "FOLDER"}:
            if option.module_path_policy is None:
                unknown.add("MODULE_PATH_POLICY_UNDECLARED")
            else:
                required.add("VERIFY_MODULE_PATH_TRANSITION:" + option.module_path_policy)
        elif option.module_path_policy is not None:
            blocked.add("MODULE_PATH_POLICY_REQUIRES_MODULE_TARGET")
        if option.proposed_name == case.current_name:
            blocked.add("NO_EFFECTIVE_NAME_CHANGE")
        if option.proposed_name in case.occupied_names:
            blocked.add("NAME_ALREADY_USED_IN_NAMESPACE")
        if not set(case.name_mismatch_evidence_ids) & refs:
            unknown.add("NAME_MISMATCH_NOT_CITED")
    if option.variant == "EXTRACT_KEEP" and case.coherence == "COHERENT":
        # Coherent code may still be modularized, but structural benefit must
        # be explained rather than inferred from naming concerns.
        if not any(known[x].kind == "EVOLUTION" for x in refs if x in known):
            unknown.add("EXTRACTION_BENEFIT_NOT_EVIDENCED")

    retained = set(option.retained_responsibility_ids)
    if not retained:
        unknown.add("RETAINED_RESPONSIBILITIES_NOT_DECLARED")
    if retained - responsibilities:
        blocked.add("INVENTED_RETAINED_RESPONSIBILITY")
    extracted = set()
    for part in option.extracted_units:
        extracted.update(part.responsibility_ids)
        if part.owner_id == case.target_id:
            blocked.add("EXTRACTION_REUSES_CURRENT_OWNER")
        if set(part.responsibility_ids) - responsibilities:
            blocked.add("INVENTED_EXTRACTED_RESPONSIBILITY")
        if set(part.seam_evidence_ids) - set(known):
            blocked.add("UNKNOWN_EXTRACTION_SEAM")
        if any(known[i].kind != "EXTRACTION_SEAM" for i in part.seam_evidence_ids if i in known):
            blocked.add("EXTRACTION_NOT_GROUNDED_IN_SEAM")
        if not set(part.seam_evidence_ids) <= refs:
            unknown.add("EXTRACTION_SEAM_NOT_CITED")
        if part.proposed_name in case.occupied_names and part.destination_path is not None:
            # Same namespace is only known for the current target; new owners
            # require independent namespace inspection at their destination.
            unknown.add("EXTRACTION_DESTINATION_NAMESPACE_CHECK_REQUIRED")
    if retained | extracted != responsibilities:
        blocked.add("RESPONSIBILITY_COVERAGE_CHANGED")
    if (option.variant == "RENAME" and retained != responsibilities):
        blocked.add("RENAME_MUST_PRESERVE_RESPONSIBILITIES")
    if option.variant in {"EXTRACT_RENAME", "EXTRACT_KEEP"}:
        if option.post_extraction_name_fit != "VALID":
            unknown.add("POST_EXTRACTION_NAME_FIT_NOT_VALIDATED")
        required.update(("VERIFY_EXTRACTION_SEAM_BEHAVIOR", "VERIFY_DESTINATION_OWNERSHIP",
                         "VERIFY_IMPORT_AND_INIT_ORDER"))
        if not all(part.destination_path for part in option.extracted_units):
            unknown.add("EXTRACTION_DESTINATION_UNRESOLVED")
    if not refs:
        unknown.add("EVIDENCE_NOT_CITED")
    if not any(known[i].kind == "BOUNDARY" for i in refs if i in known):
        unknown.add("NEGATIVE_RESPONSIBILITY_BOUNDARY_NOT_CITED")
    if not any(known[i].kind == "CONTEXT" for i in refs if i in known):
        unknown.add("REPOSITORY_NAMING_CONTEXT_NOT_CITED")
    if not all((option.coverage_rationale.strip(), option.boundary_rationale.strip(),
                option.context_rationale.strip())):
        unknown.add("CANDIDATE_SCOPE_EXPLANATION_MISSING")
    if not option.impact_paths:
        unknown.add("IMPACT_PATHS_NOT_DECLARED")
    required.update(("INDEPENDENT_NAME_SCOPE_AND_BOUNDARY_REVIEW",
                     "VERIFY_NAMING_IDEMPOTENCE", "CHECK_EXACT_BEFORE_AFTER_HEAD", "VERIFY_ALL_REFERENCES_AND_CONSUMERS",
                     "VERIFY_PUBLIC_AND_DYNAMIC_CONTRACTS", "VERIFY_SEMANTIC_COMPATIBILITY",
                     "REPLAY_REGRESSION_TESTS", "POST_CHANGE_VERIFY_AND_ROLLBACK_BOUNDARY"))
    disposition = "REJECTED" if blocked else "HOLD" if unknown else "REVIEWABLE"
    return NamingOptionReview(option.id, disposition, tuple(sorted(blocked)),
                              tuple(sorted(unknown)), tuple(sorted(required)))


def to_planning_alternative(case: NamingCase, option: NamingOption):
    """Bridge to existing refactor/planning owner; no new change execution path."""
    reviewed = review_naming_option(case, option)
    if reviewed.disposition in {"REJECTED", "HOLD"}:
        raise ValueError("NAMING_OPTION_NOT_READY_FOR_PLANNING")
    from .planning import PlanningAlternative
    change = option.variant not in {"KEEP", "HOLD"}
    created = tuple(sorted({u.destination_path for u in option.extracted_units
                            if u.destination_path is not None and not u.destination_existing}))
    affected = tuple(sorted(set(option.impact_paths) | {
        u.destination_path for u in option.extracted_units
        if u.destination_existing and u.destination_path is not None
    }))
    return PlanningAlternative(
        id=option.id, action="CHANGE" if change else "KEEP",
        description=option.rationale, affected_paths=affected,
        created_paths=created, evidence_ids=option.evidence_ids,
        assumptions=("NAMING_SEMANTICS_UNVERIFIED",) if change else (),
        expected_benefits=("NAME_RESPONSIBILITY_ALIGNMENT_TO_BE_VERIFIED",) if change else (),
        risks=("EXTERNAL_CONSUMER_OR_SEMANTIC_REGRESSION",) if change else (),
        required_checks=reviewed.required_checks,
    )


@dataclass(frozen=True, slots=True)
class RejectedNamingCandidate:
    """A comparative argument, not a machine-verified semantic judgement."""

    option_id: str
    reason: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonempty(self.option_id, "REJECTED_OPTION_ID")
        _nonempty(self.reason, "REJECTION_REASON")
        _names(self.evidence_ids, "REJECTION_EVIDENCE")
        if not self.evidence_ids:
            raise ValueError("REJECTION_WITHOUT_EVIDENCE")


@dataclass(frozen=True, slots=True)
class NamingRecommendation:
    """GPT suggestion. Independent source and semantic checks still required."""

    selected_option_id: str
    why_not_keep: str
    keep_counterevidence_ids: tuple[str, ...]
    rejected_candidates: tuple[RejectedNamingCandidate, ...]
    rationale: str
    unresolved_questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.selected_option_id, "SELECTED_OPTION_ID")
        _nonempty(self.rationale, "RECOMMENDATION_RATIONALE")
        _names(self.keep_counterevidence_ids, "KEEP_COUNTEREVIDENCE")
        _names(self.unresolved_questions, "UNRESOLVED_QUESTIONS")
        if not isinstance(self.rejected_candidates, tuple) or any(
                not isinstance(c, RejectedNamingCandidate) for c in self.rejected_candidates):
            raise TypeError("INVALID_REJECTED_CANDIDATES")
        _names(tuple(c.option_id for c in self.rejected_candidates),
               "REJECTED_CANDIDATE_IDS")


@dataclass(frozen=True, slots=True)
class NamingDecisionReceipt:
    """Only a bounded review disposition; NEVER a Git mutation permission."""

    recommended_option_id: str | None
    disposition: str  # KEEP / RECOMMEND_FOR_VERIFICATION / HOLD
    blockers: tuple[str, ...]
    unresolved: tuple[str, ...]
    required_checks: tuple[str, ...]
    provenance: str

    @property
    def mutation_approved(self) -> bool:
        return False


def build_naming_recommendation_brief(
        case: NamingCase, options: tuple[NamingOption, ...]) -> dict:
    """A bounded input protocol for GPT, not a prompt to manufacture evidence.

    The source evidence and the candidate proposals must originate outside this
    function; the model is *not* entrusted with validating its own citations.
    """
    if not isinstance(case, NamingCase):
        raise TypeError("NAMING_CASE_REQUIRED")
    if not isinstance(options, tuple) or any(not isinstance(o, NamingOption) for o in options):
        raise TypeError("NAMING_OPTIONS_REQUIRED")
    _names(tuple(o.id for o in options), "OPTION_IDS")
    if sum(o.variant == "KEEP" for o in options) != 1:
        raise ValueError("EXACTLY_ONE_KEEP_BASELINE_REQUIRED")
    return {
        "revision": case.revision,
        "target": {"kind": case.target_kind, "id": case.target_id,
                   "path": case.current_path, "name": case.current_name},
        "source_claims": [
            {"id": e.id, "kind": e.kind, "statement": e.statement,
             "revision": e.source_revision, "refs": list(e.source_refs)}
            for e in case.evidence
        ],
        "assessments_not_verified": {
            "name_fit": case.name_fit,
            "coherence": case.coherence,
            "identity": case.identity_status,
        },
        "options": [
            {"id": o.id, "variant": o.variant, "name": o.proposed_name,
             "rationale": o.rationale, "evidence_ids": list(o.evidence_ids),
             "module_path_policy": o.module_path_policy,
             "coverage": o.coverage_rationale, "excluded_boundary": o.boundary_rationale,
             "context": o.context_rationale,
             "extracted_owners": [p.owner_id for p in o.extracted_units]}
            for o in options
        ],
        "rules": [
            "Keep the existing name when it still covers the observed coherent responsibility.",
            "Do not use speculative future functionality to justify any change.",
            "Compare KEEP against every non-KEEP candidate and cite observed evidence IDs.",
            "Distinguish name-only defects from responsibility mixing or duplicated owners.",
            "For extraction, distinguish what stays from what moves and reuse the current owner.",
            "For module path changes, explicitly distinguish preserving compatibility from retiring the old path.",
            "Propose the least sufficient abstraction covering observed positive responsibilities",
            "without implying excluded responsibilities or creating ambiguous sibling names.",
            "If there is no unique supported winner, choose HOLD; do not force a name.",
            "Source refs and your semantic assertions will be checked independently.",
        ],
        "output_contract": {
            "selected_option_id": "exact option ID",
            "why_not_keep": "concrete counterexample to keeping the current name, if change",
            "keep_counterevidence_ids": "source-linked mismatch IDs, if change",
            "rejected_candidates": "each non-selected alternative with reason and evidence IDs",
            "unresolved_questions": "all remaining blockers; cannot be silently dropped",
        },
    }


def adjudicate_naming_recommendation(
        case: NamingCase, options: tuple[NamingOption, ...],
        suggestion: NamingRecommendation, provider) -> NamingDecisionReceipt:
    """Verify source anchors, then check comparative completeness; no execution.

    IMPORTANT: caller-provided name-fit and responsibility statements are still
    interpretive hypotheses. The verifier authenticates lines, NOT their meaning.
    """
    from ..verification.naming_provenance import verify_naming_evidence_sources
    if not isinstance(case, NamingCase) or not isinstance(suggestion, NamingRecommendation):
        raise TypeError("NAMING_RECOMMENDATION_INPUT_REQUIRED")
    build_naming_recommendation_brief(case, options)
    refs = {e.id: e for e in case.evidence}
    candidates = {o.id: o for o in options}
    provenance = verify_naming_evidence_sources(case, provider)
    blockers: set[str] = set(provenance.failures)
    unknown: set[str] = set(case.unknowns) | set(provenance.unresolved)
    required: set[str] = set()
    if suggestion.selected_option_id not in candidates:
        blockers.add("UNKNOWN_RECOMMENDED_OPTION")
    unknown_rejections = {r.option_id for r in suggestion.rejected_candidates} - set(candidates)
    if unknown_rejections:
        blockers.add("REJECTS_UNKNOWN_OPTION")
    for rejected in suggestion.rejected_candidates:
        if set(rejected.evidence_ids) - set(refs):
            blockers.add("REJECTION_WITH_UNKNOWN_EVIDENCE")
    if set(suggestion.keep_counterevidence_ids) - set(refs):
        blockers.add("KEEP_REBUTTAL_WITH_UNKNOWN_EVIDENCE")
    if suggestion.selected_option_id in {r.option_id for r in suggestion.rejected_candidates}:
        blockers.add("SELECTED_OPTION_ALSO_REJECTED")
    expected_rejections = set(candidates) - {suggestion.selected_option_id}
    if expected_rejections != {r.option_id for r in suggestion.rejected_candidates}:
        unknown.add("COMPETING_OPTIONS_NOT_ALL_COMPARED")
    if provenance.status != "SOURCE_ANCHORS_VERIFIED":
        unknown.add("SOURCE_PROVENANCE_NOT_COMPLETE")
    if case.identity_status != "RESOLVED":
        unknown.add("LOGICAL_IDENTITY_UNRESOLVED")
    if any(refs[rid].source_revision != case.revision
           for rid in case.responsibility_ids if rid in refs):
        unknown.add("CURRENT_RESPONSIBILITY_WITNESS_MISSING")
    if case.name_fit == "UNKNOWN" or case.coherence == "UNKNOWN":
        unknown.add("RESPONSIBILITY_OR_NAME_FIT_UNRESOLVED")
    selected = candidates.get(suggestion.selected_option_id)
    if selected is not None:
        review = review_naming_option(case, selected)
        blockers.update(review.blockers)
        unknown.update(review.unknowns)
        required.update(review.required_checks)
        if review.disposition in {"HOLD", "REJECTED"}:
            unknown.add("SELECTED_OPTION_NOT_REVIEWABLE")
        if selected.variant == "HOLD":
            unknown.add("GPT_SELECTED_HOLD")
        elif selected.variant == "KEEP":
            if case.name_fit != "VALID":
                unknown.add("KEEP_NOT_INDEPENDENTLY_JUSTIFIED")
        else:
            if case.name_fit == "VALID" and selected.variant in {"RENAME", "EXTRACT_RENAME"}:
                blockers.add("STABLE_VALID_NAME_MUST_BE_KEPT")
            if not suggestion.why_not_keep.strip():
                unknown.add("WHY_NOT_KEEP_MISSING")
            if not suggestion.keep_counterevidence_ids:
                unknown.add("KEEP_COUNTEREVIDENCE_MISSING")
            if selected.variant in {"RENAME", "EXTRACT_RENAME"}:
                if not any(refs[i].kind == "NAME_MISMATCH"
                           for i in suggestion.keep_counterevidence_ids if i in refs):
                    unknown.add("KEEP_NOT_REFUTED_BY_NAME_MISMATCH")
            elif selected.variant == "EXTRACT_KEEP":
                if not any(refs[i].kind == "EXTRACTION_SEAM"
                           for i in suggestion.keep_counterevidence_ids if i in refs):
                    unknown.add("KEEP_NOT_REFUTED_BY_EXTRACTION_SEAM")
            if not any(refs[i].kind == "EVOLUTION"
                       for i in selected.evidence_ids if i in refs):
                unknown.add("EVOLUTION_BASIS_MISSING")
            if not any(refs[i].kind == "EVOLUTION" and
                       refs[i].source_revision != case.revision
                       for i in selected.evidence_ids if i in refs):
                unknown.add("HISTORICAL_EVOLUTION_WITNESS_MISSING")
            if selected.variant in {"RENAME", "EXTRACT_RENAME"}:
                if not any(refs[i].kind == "NAME_MISMATCH" and
                           refs[i].source_revision == case.revision
                           for i in suggestion.keep_counterevidence_ids if i in refs):
                    unknown.add("CURRENT_NAME_MISMATCH_WITNESS_MISSING")
            required.update(("INDEPENDENT_SEMANTIC_NAME_AND_BOUNDARY_REVIEW",
                             "VERIFY_NAME_STABILITY_ON_REAUDIT"))
    # If any reviewable alternative is left unexplained, the model did not
    # establish why this choice is preferable. Arguments alone are not proof.
    for o in options:
        if o.id == suggestion.selected_option_id:
            continue
        review = review_naming_option(case, o)
        if review.disposition in {"REVIEWABLE", "BASELINE"} and not any(
                r.option_id == o.id for r in suggestion.rejected_candidates):
            unknown.add("UNADDRESSED_VIABLE_COMPETITOR:" + o.id)
    if suggestion.unresolved_questions:
        unknown.add("GPT_DISCLOSED_UNRESOLVED_QUESTIONS")
    if blockers or unknown:
        disposition = "HOLD"
        selected_id = None
    elif selected is not None and selected.variant == "KEEP":
        disposition = "KEEP"
        selected_id = selected.id
    else:
        disposition = "RECOMMEND_FOR_VERIFICATION"
        selected_id = selected.id if selected else None
    return NamingDecisionReceipt(selected_id, disposition,
                                 tuple(sorted(blockers)), tuple(sorted(unknown)),
                                 tuple(sorted(required)), provenance.status)

__all__ = ["NamingEvidence", "NamingCase", "ExtractionUnit", "NamingOption",
           "NamingOptionReview", "review_naming_option", "to_planning_alternative",
           "RejectedNamingCandidate", "NamingRecommendation", "NamingDecisionReceipt",
           "build_naming_recommendation_brief", "adjudicate_naming_recommendation"]
