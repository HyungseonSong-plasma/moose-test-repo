"""Planning v0.1: read-only evidence and general evidence and constraint boundaries."""

from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace as Obj
import unittest

from physics_harness.code.refactor import (
    ConstraintCheck, HardConstraint, PlanningAlternative, PlanningAssessment,
    build_planning_context, validate_alternative,
)


SHA = "a" * 40
BLOB = "b" * 40
PATH = "src/example.py"


def diagnostic(*, source_status="SCANNED", provenance_status="VERIFIED",
               unrelated=False):
    target = Obj(
        id="node:target", name="example", qualified_name="src/example.py:example",
        location=Obj(path=PATH),
        attributes={"loc": 15, "branches": 2, "max_branch_nesting": 1,
                    "hu_score": 99},
        evidence_ids=("ev:target",),
    )
    nodes = {"node:target": target}
    edges = [Obj(source_id="node:target", target_id="node:callee",
                 relation="CALLS_CANDIDATE", evidence_ids=("ev:call",))]
    if unrelated:
        nodes["node:other"] = Obj(id="node:other", name="other",
            qualified_name="src/example.py:other", location=Obj(path=PATH),
            attributes={}, evidence_ids=("ev:other",))
    evidence = {s: Obj(id=s) for s in ("ev:target", "ev:call", "ev:other")}
    graph = Obj(
        scope=Obj(repository="sample/repo", revision=SHA, id="scope:1", completeness="COMPLETE",
                  unresolved=()),
        nodes_by_id=lambda: nodes,
        evidence_by_id=lambda: evidence,
        edges=edges,
    )
    receipt = Obj(
        repository="sample/repo", revision=SHA, scope_id="scope:1", completeness="COMPLETE",
        files=(Obj(path=PATH, blob_sha=BLOB, status=source_status),),
        unresolved=(),
    )
    verification = Obj(
        repository="sample/repo", revision=SHA, scope_id="scope:1",
        status=provenance_status,
        unverified_properties=("SEMANTIC_COMPATIBILITY_UNPROVEN",),
    )
    return Obj(graph=graph, receipt=receipt, verification=verification)


def ctx(*, constraints=(), assessments=(), **diagnostic_overrides):
    return build_planning_context(
        diagnostic(**diagnostic_overrides), "node:target",
        objectives=("Improve relationship transparency",),
        hard_constraints=constraints, assessments=assessments,
    )


def change(**kwargs):
    defaults = dict(
        id="candidate-a", action="CHANGE", description="Consider a keyed index",
        affected_paths=(PATH,), evidence_ids=("ev:target",),
        expected_benefits=("Potentially simpler lookup",),
        risks=("Ordering and duplicate matches could change",),
    )
    defaults.update(kwargs)
    return PlanningAlternative(**defaults)


class PlanningTests(unittest.TestCase):
    def test_build_from_diagnostic_preserves_revision_blob_and_metrics(self):
        result = ctx()
        self.assertEqual((result.revision, result.source_blob_sha), (SHA, BLOB))
        self.assertEqual(result.structural_metrics,
            (("loc", 15), ("branches", 2), ("max_branch_nesting", 1)))
        self.assertNotIn(("hu_score", 99), result.structural_metrics)
        self.assertEqual(result.candidate_relations, ("CALLS_CANDIDATE",))
        self.assertEqual(result.target_evidence_ids, ("ev:call", "ev:target"))
        self.assertIn("SEMANTIC_COMPATIBILITY_UNPROVEN", result.unknowns)
        self.assertFalse(result.mutation_approved)

    def test_admissible_means_reviewable_not_safe_to_edit(self):
        verdict = validate_alternative(ctx(), change())
        self.assertEqual(verdict.disposition, "ADMISSIBLE")
        self.assertFalse(verdict.mutation_approved)
        self.assertIn("VERIFY_BEHAVIORAL_COMPATIBILITY", verdict.required_checks)
        self.assertIn("REPLAY_IMPACTED_TESTS_AT_AFTER_HEAD", verdict.required_checks)

    def test_keep_is_supported_without_strategy_catalogue(self):
        keep = PlanningAlternative("baseline", "KEEP", "Keep current code")
        self.assertEqual(validate_alternative(ctx(), keep).disposition, "ADMISSIBLE")
        bad_keep = replace(keep, affected_paths=(PATH,))
        self.assertEqual(validate_alternative(ctx(), bad_keep).disposition, "BLOCKED")

    def test_assessment_is_not_conflated_with_static_ast_metrics(self):
        assessment = PlanningAssessment("HU", "REVIEW_REQUIRED",
            "No measured user rating", ("ev:target",))
        result = ctx(assessments=(assessment,))
        self.assertEqual(result.assessments, (assessment,))
        self.assertFalse(any(n == "HU" for n, _ in result.structural_metrics))

    def test_nonexistent_assessment_evidence_is_rejected(self):
        bad = PlanningAssessment("HU", "OBSERVED", "Bad source", ("ev:missing",))
        with self.assertRaisesRegex(ValueError, "UNKNOWN_ASSESSMENT_EVIDENCE"):
            ctx(assessments=(bad,))

    def test_cross_revision_receipt_is_rejected(self):
        scan = diagnostic()
        scan.receipt.revision = "c" * 40
        with self.assertRaisesRegex(ValueError, "PLANNING_SCOPE_RECEIPT_MISMATCH"):
            build_planning_context(scan, "node:target")

    def test_cross_revision_verification_is_rejected(self):
        scan = diagnostic()
        scan.verification.revision = "c" * 40
        with self.assertRaisesRegex(ValueError, "PLANNING_VERIFICATION_SCOPE_MISMATCH"):
            build_planning_context(scan, "node:target")

    def test_unknown_target_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "UNKNOWN_PLANNING_TARGET"):
            build_planning_context(diagnostic(), "node:invented")

    def test_unverified_source_forces_hold(self):
        verdict = validate_alternative(ctx(provenance_status="UNVERIFIED"), change())
        self.assertEqual(verdict.disposition, "HOLD")
        self.assertIn("SOURCE_PROVENANCE_UNVERIFIED", verdict.unknowns)

    def test_provenance_failure_blocks(self):
        verdict = validate_alternative(ctx(provenance_status="FAILED"), change())
        self.assertEqual(verdict.disposition, "BLOCKED")
        self.assertIn("SOURCE_PROVENANCE_FAILED", verdict.blockers)

    def test_source_not_scanned_forces_hold(self):
        verdict = validate_alternative(ctx(source_status="UNRESOLVED"), change())
        self.assertEqual(verdict.disposition, "HOLD")

    def test_unknown_evidence_is_blocked_not_invented(self):
        verdict = validate_alternative(ctx(unrelated=True), change(evidence_ids=("ev:fake",)))
        self.assertEqual(verdict.disposition, "BLOCKED")
        self.assertIn("UNKNOWN_ALTERNATIVE_EVIDENCE", verdict.blockers)

    def test_unrelated_evidence_is_not_sufficient(self):
        verdict = validate_alternative(ctx(unrelated=True), change(evidence_ids=("ev:other",)))
        self.assertEqual(verdict.disposition, "HOLD")
        self.assertIn("TARGET_EVIDENCE_NOT_CITED", verdict.unknowns)

    def test_outside_scope_needs_additional_scan(self):
        verdict = validate_alternative(ctx(), change(affected_paths=("src/other.py",)))
        self.assertEqual(verdict.disposition, "HOLD")
        self.assertIn("PATH_OUTSIDE_VERIFIED_SOURCE_SCOPE:src/other.py", verdict.unknowns)

    def test_missing_independent_constraint_check_holds(self):
        constraint = HardConstraint("no_api_change", "Preserve public API")
        verdict = validate_alternative(ctx(constraints=(constraint,)), change())
        self.assertEqual(verdict.disposition, "HOLD")
        self.assertIn("CONSTRAINT_NOT_EVALUATED:no_api_change", verdict.unknowns)

    def test_independent_pass_is_reviewable_but_not_approved(self):
        constraint = HardConstraint("no_api_change", "Preserve public API")
        check = ConstraintCheck("no_api_change", "candidate-a", SHA, "PASS", "unit-test:api-baseline")
        verdict = validate_alternative(ctx(constraints=(constraint,)), change(),
                                       constraint_checks=(check,))
        self.assertEqual(verdict.disposition, "ADMISSIBLE")
        self.assertFalse(verdict.mutation_approved)
        self.assertNotIn("CHECK_CONSTRAINT:no_api_change", verdict.required_checks)

    def test_independent_failure_blocks(self):
        constraint = HardConstraint("preserve_ids", "Keep canonical node IDs")
        check = ConstraintCheck("preserve_ids", "candidate-a", SHA, "FAIL", "graph-diff:change-12")
        verdict = validate_alternative(ctx(constraints=(constraint,)), change(),
                                       constraint_checks=(check,))
        self.assertEqual(verdict.disposition, "BLOCKED")
        self.assertIn("CONSTRAINT_FAILED:preserve_ids", verdict.blockers)

    def test_unverified_check_holds(self):
        constraint = HardConstraint("order", "Preserve first match")
        check = ConstraintCheck("order", "candidate-a", SHA, "UNVERIFIED", "test:priority-boundary")
        verdict = validate_alternative(ctx(constraints=(constraint,)), change(),
                                       constraint_checks=(check,))
        self.assertEqual(verdict.disposition, "HOLD")

    def test_check_for_unknown_constraint_is_blocked(self):
        check = ConstraintCheck("invented", "candidate-a", SHA, "PASS", "untrusted:assertion")
        verdict = validate_alternative(ctx(), change(), constraint_checks=(check,))
        self.assertEqual(verdict.disposition, "BLOCKED")

    def test_missing_or_invalid_path_rejected(self):
        with self.assertRaises(ValueError):
            change(affected_paths=("../outside.py",))
        with self.assertRaises(ValueError):
            change(affected_paths=("/absolute.py",))

    def test_proposed_change_without_benefit_or_risk_holds(self):
        verdict = validate_alternative(ctx(), change(expected_benefits=(), risks=()))
        self.assertEqual(verdict.disposition, "HOLD")
        self.assertIn("RISK_ASSESSMENT_MISSING", verdict.unknowns)
        self.assertIn("EXPECTED_BENEFIT_UNDECLARED", verdict.unknowns)

    def test_measured_hu_requires_source_reference(self):
        with self.assertRaisesRegex(ValueError, "MEASURED_ASSESSMENT_REQUIRES_SOURCE"):
            PlanningAssessment("HU", "MEASURED", "measured")
        wrong = PlanningAssessment("HU", "MEASURED", "measured", ("ev:target",), "d" * 40)
        with self.assertRaisesRegex(ValueError, "ASSESSMENT_SOURCE_REVISION_MISMATCH"):
            ctx(assessments=(wrong,))

    def test_keep_cannot_override_failed_source(self):
        keep = PlanningAlternative("baseline", "KEEP", "Keep current code")
        self.assertEqual(validate_alternative(
            ctx(provenance_status="FAILED"), keep).disposition, "BLOCKED")

    def test_duplicate_constraints_are_rejected(self):
        repeated = HardConstraint("same", "An invariant")
        with self.assertRaisesRegex(ValueError, "DUPLICATE_CONSTRAINT_ID"):
            ctx(constraints=(repeated, repeated))

    def test_missing_target_evidence_holds(self):
        verdict = validate_alternative(ctx(), change(evidence_ids=()))
        self.assertEqual(verdict.disposition, "HOLD")
        self.assertIn("TARGET_EVIDENCE_NOT_CITED", verdict.unknowns)

    def test_duplicate_check_is_rejected(self):
        constraint = HardConstraint("ordering", "Preserve order")
        check = ConstraintCheck("ordering", "candidate-a", SHA, "PASS", "test:123")
        with self.assertRaisesRegex(ValueError, "DUPLICATE_CONSTRAINT_CHECK"):
            validate_alternative(ctx(constraints=(constraint,)), change(),
                                 constraint_checks=(check, check))

    def test_stale_or_cross_alternative_checker_is_rejected(self):
        constraint = HardConstraint("order", "Preserve order")
        stale = ConstraintCheck("order", "candidate-a", "f" * 40, "PASS", "test:old")
        wrong = ConstraintCheck("order", "candidate-b", SHA, "PASS", "test:other")
        for check, expected in (
            (stale, "CHECK_FOR_ANOTHER_REVISION:order"),
            (wrong, "CHECK_FOR_ANOTHER_ALTERNATIVE:order"),
        ):
            result = validate_alternative(
                ctx(constraints=(constraint,)), change(), constraint_checks=(check,))
            self.assertEqual(result.disposition, "BLOCKED")
            self.assertIn(expected, result.blockers)

    def test_frozen_input_and_no_mutation(self):
        result = ctx()
        with self.assertRaises(FrozenInstanceError):
            result.revision = "c" * 40
        self.assertFalse(result.mutation_approved)


if __name__ == "__main__":
    unittest.main()


def test_plan_preserves_inherited_unknowns_without_inventing_verification():
    result = validate_alternative(ctx(), change())
    assert result.disposition == "ADMISSIBLE"
    assert "SEMANTIC_COMPATIBILITY_UNPROVEN" in result.unknowns
    assert not result.mutation_approved


def test_keep_does_not_require_change_preservation_checks():
    constraint = HardConstraint("stable_api", "Preserve existing public API")
    result = validate_alternative(ctx(constraints=(constraint,)),
                                  PlanningAlternative("unchanged", "KEEP", "Keep it"))
    assert result.disposition == "ADMISSIBLE"
    assert "CHECK_CONSTRAINT:stable_api" not in result.required_checks


def test_keep_does_not_hide_explicit_constraint_failure():
    constraint = HardConstraint("stable_api", "Preserve existing public API")
    check = ConstraintCheck("stable_api", "unchanged", SHA, "FAIL", "fixture:known-bad")
    result = validate_alternative(ctx(constraints=(constraint,)),
                                  PlanningAlternative("unchanged", "KEEP", "Keep it"),
                                  constraint_checks=(check,))
    assert result.disposition == "BLOCKED"
    assert "CONSTRAINT_FAILED:stable_api" in result.blockers


def test_partial_scope_remains_visible_to_planning():
    scan = diagnostic()
    scan.graph.scope.completeness = "PARTIAL"
    scan.receipt.completeness = "PARTIAL"
    context = build_planning_context(scan, "node:target")
    assert "INCOMPLETE_PLANNING_SCOPE" in context.unknowns
    verdict = validate_alternative(context, PlanningAlternative("unchanged", "KEEP", "Keep"))
    assert "INCOMPLETE_PLANNING_SCOPE" in verdict.unknowns
