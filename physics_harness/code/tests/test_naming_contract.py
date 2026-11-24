"""P0: stability-first naming decisions and extraction-ownership counterexamples."""
from dataclasses import replace

import pytest

from physics_harness.code.refactor.naming import (
    ExtractionUnit, NamingCase, NamingEvidence, NamingOption, review_naming_option,
)

BLOB = "a" * 40
HEAD = "b" * 40


def ev(id, kind):
    return NamingEvidence(id, kind, id.replace("_", " "), (f"physics_harness/code/diagnostics/collector.py:12@{BLOB}",), HEAD)


def case(*, name_fit="NARROW", coherence="COHERENT", identity_status="RESOLVED"):
    e = tuple(ev(id, kind) for id, kind in (
        ("collect", "RESPONSIBILITY"),
        ("python", "RESPONSIBILITY"),
        ("cpp", "RESPONSIBILITY"),
        ("moose", "RESPONSIBILITY"),
        ("narrow", "NAME_MISMATCH"),
        ("boundary", "BOUNDARY"),
        ("context", "CONTEXT"),
        ("seam", "EXTRACTION_SEAM"),
        ("evolution", "EVOLUTION"),
    ))
    return NamingCase("HyungseonSong-plasma/moose-test-repo", HEAD,
                      "FILE", "logical-collector", "python_collector",
                      "diagnostics/python_collector.py",
                      ("collect", "python", "cpp", "moose"), e,
                      identity_status, coherence, name_fit,
                      ("narrow",) if name_fit in {"NARROW", "MISLEADING"} else (),
                      ("worker",))


def option(*, variant="RENAME", proposed_name="collector", extracted_units=(),
           retained=("collect", "python", "cpp", "moose"),
           evidence_ids=("narrow", "boundary", "context", "evolution")):
    return NamingOption(
        "candidate", variant, "Responsibility-bound generalization",
        proposed_name=proposed_name, extracted_units=extracted_units,
        module_path_policy="RETIRE_OLD_PATH" if variant in {"RENAME", "EXTRACT_RENAME"} else None,
        retained_responsibility_ids=retained, evidence_ids=evidence_ids,
        coverage_rationale="Collect source facts across supported input kinds",
        boundary_rationale="Does not assess, plan or execute changes",
        context_rationale="Diagnostics parent supplies the collection domain",
        impact_paths=("diagnostics/python_collector.py",),
        post_extraction_name_fit="VALID" if variant.startswith("EXTRACT_") else None,
    )


def extraction():
    return ExtractionUnit("python-provider", "python", ("python",), ("seam",),
                          "diagnostics/providers/python.py")


def test_mismatched_but_coherent_name_is_reviewable_not_executable():
    reviewed = review_naming_option(case(), option())
    assert reviewed.disposition == "REVIEWABLE"
    assert not reviewed.mutation_approved
    assert "VERIFY_SEMANTIC_COMPATIBILITY" in reviewed.required_checks
    assert "INDEPENDENT_NAME_SCOPE_AND_BOUNDARY_REVIEW" in reviewed.required_checks


def test_currently_valid_generic_name_stays_keep():
    subject = replace(case(name_fit="VALID"), current_name="collector")
    old = NamingOption("keep", "KEEP", "Stable responsibility name")
    assert review_naming_option(subject, old).disposition == "BASELINE"
    renamed = replace(option(), proposed_name="source_fact_collector")
    assert review_naming_option(subject, renamed).disposition == "REJECTED"


def test_name_swap_cannot_force_a_rename_from_valid_name():
    subject = replace(case(name_fit="VALID"), current_name="source_collector")
    reviewed = review_naming_option(subject, replace(option(), proposed_name="collector"))
    assert "VALID_NAME_DOES_NOT_REQUIRE_RENAME" in reviewed.blockers


def test_rename_alone_does_not_fix_mixed_responsibilities():
    assert "MIXED_RESPONSIBILITIES_CANNOT_BE_FIXED_BY_RENAME" in review_naming_option(
        case(coherence="MIXED"), option()).blockers


def test_extraction_and_rename_preserve_responsibility_coverage_and_seam():
    candidate = option(variant="EXTRACT_RENAME", retained=("collect", "cpp", "moose"),
                       extracted_units=(extraction(),),
                       evidence_ids=("narrow", "boundary", "context", "seam", "evolution"))
    reviewed = review_naming_option(case(coherence="MIXED"), candidate)
    assert reviewed.disposition == "REVIEWABLE"
    assert "VERIFY_EXTRACTION_SEAM_BEHAVIOR" in reviewed.required_checks
    assert not reviewed.mutation_approved


def test_extraction_without_rename_allowed_for_stable_name():
    candidate = option(variant="EXTRACT_KEEP", proposed_name=None,
                       retained=("collect", "cpp", "moose"), extracted_units=(extraction(),),
                       evidence_ids=("seam", "boundary", "context", "evolution"))
    reviewed = review_naming_option(case(name_fit="VALID"), candidate)
    assert reviewed.disposition == "REVIEWABLE"


def test_extraction_without_rename_requires_structural_evidence_if_coherent():
    candidate = option(variant="EXTRACT_KEEP", proposed_name=None,
                       retained=("collect", "cpp", "moose"), extracted_units=(extraction(),),
                       evidence_ids=("seam", "boundary", "context"))
    assert "EXTRACTION_BENEFIT_NOT_EVIDENCED" in review_naming_option(
        case(name_fit="VALID"), candidate).unknowns


def test_extraction_cannot_drop_an_existing_responsibility():
    candidate = option(variant="EXTRACT_RENAME", retained=("collect", "cpp"),
                       extracted_units=(extraction(),),
                       evidence_ids=("narrow", "boundary", "context", "seam", "evolution"))
    assert "RESPONSIBILITY_COVERAGE_CHANGED" in review_naming_option(
        case(coherence="MIXED"), candidate).blockers


def test_extraction_cannot_invent_responsibility():
    rogue = replace(extraction(), responsibility_ids=("database_admin",))
    candidate = option(variant="EXTRACT_RENAME", retained=("collect", "python", "cpp", "moose"),
                       extracted_units=(rogue,), evidence_ids=("narrow", "boundary", "context", "seam", "evolution"))
    assert "INVENTED_EXTRACTED_RESPONSIBILITY" in review_naming_option(
        case(coherence="MIXED"), candidate).blockers


def test_rename_requires_actual_mismatch_evidence():
    o = replace(option(), evidence_ids=("boundary", "context", "evolution"))
    assert "NAME_MISMATCH_NOT_CITED" in review_naming_option(case(), o).unknowns


def test_name_recommendation_without_negative_boundary_is_unproven():
    o = replace(option(), evidence_ids=("narrow", "context", "evolution"))
    assert "NEGATIVE_RESPONSIBILITY_BOUNDARY_NOT_CITED" in review_naming_option(case(), o).unknowns


def test_name_recommendation_without_repo_context_is_unproven():
    o = replace(option(), evidence_ids=("narrow", "boundary", "evolution"))
    assert "REPOSITORY_NAMING_CONTEXT_NOT_CITED" in review_naming_option(case(), o).unknowns


def test_missing_candidate_naming_scope_explanations_hold():
    o = replace(option(), boundary_rationale="")
    assert "CANDIDATE_SCOPE_EXPLANATION_MISSING" in review_naming_option(case(), o).unknowns


def test_unknown_logical_identity_blocks_automatic_progress():
    assert "LOGICAL_IDENTITY_UNRESOLVED" in review_naming_option(
        case(identity_status="UNKNOWN"), option()).unknowns


def test_same_namespace_collision_is_rejected():
    assert "NAME_ALREADY_USED_IN_NAMESPACE" in review_naming_option(
        case(), replace(option(), proposed_name="worker")).blockers


def test_unknown_name_fit_holds_without_force():
    reviewed = review_naming_option(case(name_fit="UNKNOWN"), option())
    assert reviewed.disposition == "HOLD"
    assert "NAME_MISMATCH_UNRESOLVED" in reviewed.unknowns


def test_fake_or_missing_evidence_rejected():
    with pytest.raises(ValueError, match="INVALID_BLOB_BOUND_SOURCE_REF"):
        NamingEvidence("x", "BOUNDARY", "a", ("no provenance",), HEAD)
    with pytest.raises(ValueError, match="MISMATCH_CLAIM_WITHOUT_EVIDENCE"):
        replace(case(), name_mismatch_evidence_ids=())


def test_keep_is_not_a_mutation():
    reviewed = review_naming_option(case(), NamingOption("keep", "KEEP", "Preserve current name"))
    assert reviewed.disposition == "BASELINE"
    assert reviewed.required_checks == ()
    assert not reviewed.mutation_approved


def test_reviewable_rename_still_requires_independent_reference_contract_checks():
    checks = review_naming_option(case(), option()).required_checks
    assert "VERIFY_ALL_REFERENCES_AND_CONSUMERS" in checks
    assert "VERIFY_PUBLIC_AND_DYNAMIC_CONTRACTS" in checks
    assert "CHECK_EXACT_BEFORE_AFTER_HEAD" in checks
    assert "VERIFY_NAMING_IDEMPOTENCE" in checks


def test_holding_cannot_claim_execution():
    out = review_naming_option(case(), NamingOption("hold", "HOLD", "Incomplete"))
    assert out.disposition == "HOLD" and not out.mutation_approved


def test_extraction_keeps_name_only_with_residual_fit_review():
    candidate = option(variant="EXTRACT_KEEP", proposed_name=None,
                       retained=("collect", "cpp", "moose"), extracted_units=(extraction(),),
                       evidence_ids=("seam", "boundary", "context", "evolution"))
    bad = replace(candidate, post_extraction_name_fit="UNKNOWN")
    assert "POST_EXTRACTION_NAME_FIT_NOT_VALIDATED" in review_naming_option(
        case(name_fit="VALID"), bad).unknowns


def test_rename_requires_evolution_evidence_not_future_speculation():
    candidate = replace(option(), evidence_ids=("narrow", "boundary", "context"))
    assert "CODE_EVOLUTION_NOT_EVIDENCED" in review_naming_option(case(), candidate).unknowns


def test_destination_existing_flag_is_explicit():
    with pytest.raises(ValueError, match="EXISTING_DESTINATION_PATH_REQUIRED"):
        replace(extraction(), destination_existing=True, destination_path=None)


def test_target_must_be_in_impact_scope():
    candidate = replace(option(), impact_paths=("diagnostics/other.py",))
    assert "TARGET_NOT_IN_IMPACT_PATHS" in review_naming_option(case(), candidate).unknowns


def test_bridge_to_existing_strategy_neutral_planner_requires_independent_checks():
    from physics_harness.code.refactor.naming import to_planning_alternative
    candidate = to_planning_alternative(case(), option())
    assert candidate.action == "CHANGE"
    assert "VERIFY_SEMANTIC_COMPATIBILITY" in candidate.required_checks
    assert candidate.assumptions == ("NAMING_SEMANTICS_UNVERIFIED",)
    assert candidate.affected_paths == ("diagnostics/python_collector.py",)


def test_bridge_create_vs_update_existing_owner():
    from physics_harness.code.refactor.naming import to_planning_alternative
    added = option(variant="EXTRACT_RENAME", retained=("collect", "cpp", "moose"),
                   extracted_units=(extraction(),),
                   evidence_ids=("narrow", "boundary", "context", "seam", "evolution"))
    as_plan = to_planning_alternative(case(coherence="MIXED"), added)
    assert as_plan.created_paths == ("diagnostics/providers/python.py",)
    existing = replace(extraction(), destination_existing=True)
    changed = replace(added, extracted_units=(existing,))
    as_plan_existing = to_planning_alternative(case(coherence="MIXED"), changed)
    assert as_plan_existing.created_paths == ()
    assert "diagnostics/providers/python.py" in as_plan_existing.affected_paths


def test_unresolved_proposal_never_reaches_canonical_planner():
    from physics_harness.code.refactor.naming import to_planning_alternative
    with pytest.raises(ValueError, match="NAMING_OPTION_NOT_READY_FOR_PLANNING"):
        to_planning_alternative(case(name_fit="UNKNOWN"), option())


def test_module_rename_requires_explicit_compatibility_or_retirement():
    missing = replace(option(), module_path_policy=None)
    assert review_naming_option(case(), missing).disposition == "HOLD"
    assert "MODULE_PATH_POLICY_UNDECLARED" in review_naming_option(case(), missing).unknowns
    for policy in ("RETIRE_OLD_PATH", "PRESERVE_COMPATIBILITY"):
        selected = replace(option(), module_path_policy=policy)
        result = review_naming_option(case(), selected)
        assert result.disposition == "REVIEWABLE"
        assert "VERIFY_MODULE_PATH_TRANSITION:" + policy in result.required_checks
    with pytest.raises(ValueError, match="INVALID_MODULE_PATH_POLICY"):
        replace(option(), module_path_policy="AUTO")
