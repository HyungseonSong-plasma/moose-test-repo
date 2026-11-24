"""Alternatives are evaluated without a strategy catalogue or implicit ranking."""

from types import SimpleNamespace as Obj
import unittest

import pytest

from physics_harness.code.refactor import (
    PlanningAlternative, build_planning_context, review_alternatives,
)

SHA = "a" * 40
BLOB = "b" * 40


def context():
    target = Obj(id="n:target", name="f", qualified_name="src/a.py:f",
                 location=Obj(path="src/a.py"),
                 attributes={"loc": 4, "branches": 1},
                 evidence_ids=("ev:t",))
    graph = Obj(scope=Obj(repository="example/repo", revision=SHA, id="scope:x", completeness="COMPLETE", unresolved=()),
                nodes_by_id=lambda: {target.id: target},
                evidence_by_id=lambda: {"ev:t": Obj(id="ev:t")}, edges=())
    receipt = Obj(repository="example/repo", revision=SHA, scope_id="scope:x", completeness="COMPLETE",
                  files=(Obj(path="src/a.py", blob_sha=BLOB, status="SCANNED"),),
                  unresolved=())
    verification = Obj(repository="example/repo", revision=SHA, scope_id="scope:x",
                       status="VERIFIED", unverified_properties=())
    result = Obj(graph=graph, receipt=receipt, verification=verification)
    return build_planning_context(result, target.id, objectives=("Preserve behavior",))


class AlternativesTests(unittest.TestCase):
    def test_keep_and_change_are_independently_validated(self):
        keep = PlanningAlternative("keep", "KEEP", "No change")
        edit = PlanningAlternative("edit", "CHANGE", "Try clearer lookup",
                                   affected_paths=("src/a.py",), evidence_ids=("ev:t",),
                                   expected_benefits=("More explicit relationship",),
                                   risks=("May change duplicate semantics",))
        report = review_alternatives(context(), (keep, edit))
        self.assertEqual(tuple(r.disposition for r in report.results),
                         ("ADMISSIBLE", "ADMISSIBLE"))
        self.assertIsNone(report.recommended_id)
        self.assertFalse(report.mutation_approved)

    def test_rejects_duplicate_alternative_names(self):
        items = (PlanningAlternative("same", "KEEP", "a"),
                 PlanningAlternative("same", "KEEP", "b"))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PLANNING_ALTERNATIVE"):
            review_alternatives(context(), items)

    def test_rejects_checks_of_undeclared_alternative(self):
        from physics_harness.code.refactor import ConstraintCheck
        check = ConstraintCheck("c", "unknown", SHA, "PASS", "record:1")
        with self.assertRaisesRegex(ValueError, "CHECK_FOR_UNKNOWN_ALTERNATIVE"):
            review_alternatives(context(), (PlanningAlternative("keep", "KEEP", "a"),),
                                constraint_checks=(check,))

    def test_empty_set_is_valid_no_auto_proposal(self):
        report = review_alternatives(context(), ())
        self.assertEqual(report.results, ())
        self.assertIsNone(report.recommended_id)


if __name__ == "__main__":
    unittest.main()


def test_review_validates_input_types():
    with pytest.raises(TypeError, match="PLANNING_CONTEXT_REQUIRED"):
        review_alternatives(None, ())
    with pytest.raises(TypeError, match="INVALID_CONSTRAINT_CHECKS"):
        review_alternatives(context(), (), constraint_checks=("not-a-check",))


def test_new_folder_destination_is_a_post_change_obligation_not_existing_source():
    edit = PlanningAlternative(
        "move", "CHANGE", "Move module without changing behavior",
        affected_paths=("src/a.py",), removed_paths=("src/a.py",),
        created_paths=("src/core/a.py",), evidence_ids=("ev:t",),
        expected_benefits=("More coherent module ownership",),
        risks=("Import paths and external consumers could break",),
    )
    result = review_alternatives(context(), (edit,)).results[0]
    assert result.disposition == "ADMISSIBLE"
    assert "VERIFY_PROPOSED_NEW_PATHS_AT_BASELINE" in result.required_checks
    assert "VERIFY_NEW_PATHS_AT_AFTER_HEAD" in result.required_checks
    assert "VERIFY_REMOVED_CONSUMERS_AND_REFERENCES" in result.required_checks


def test_claiming_creation_at_existing_scanned_path_blocks():
    with pytest.raises(ValueError, match="CREATED_PATH_OVERLAPS_EXISTING_PATH"):
        PlanningAlternative("duplicate", "CHANGE", "not valid", created_paths=("src/a.py",),
                            affected_paths=("src/a.py",))


def test_keep_may_not_request_path_creation_or_deletion():
    result = review_alternatives(context(), (
        PlanningAlternative("keep", "KEEP", "No change", created_paths=("new/file.py",)),
    )).results[0]
    assert result.disposition == "BLOCKED"


def test_deleted_unscanned_path_is_uncertain():
    edit = PlanningAlternative(
        "remove", "CHANGE", "Remove unused file", affected_paths=("src/a.py",),
        removed_paths=("not-scanned/file.py",), evidence_ids=("ev:t",),
        expected_benefits=("Smaller source tree",), risks=("Unknown consumers",),
    )
    result = review_alternatives(context(), (edit,)).results[0]
    assert result.disposition == "HOLD"
    assert any(x.startswith("REMOVED_PATH_OUTSIDE") for x in result.unknowns)
