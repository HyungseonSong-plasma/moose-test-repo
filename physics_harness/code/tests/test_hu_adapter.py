"""HU integration boundary tests using diagnostic-shaped immutable observations."""

from types import SimpleNamespace as Obj
from dataclasses import replace
import unittest

from libs.hu import HUObservation
from physics_harness.code.analysis.hu_adapter import assess_code_hu

REV = "a" * 40
BLOB = "b" * 40
PATH = "src/source.py"


def diagnostic(*, verification="VERIFIED", source_status="SCANNED", attributes=None):
    node = Obj(id="n:f", location=Obj(path=PATH),
               attributes={"loc": 4, "branches": 1, "max_branch_nesting": 1}
                          if attributes is None else attributes,
               evidence_ids=("ev:decl",))
    scope = Obj(repository="demo/repo", revision=REV, id="scope:1", unresolved=())
    graph = Obj(scope=scope, nodes_by_id=lambda: {node.id: node})
    receipt = Obj(repository="demo/repo", revision=REV, scope_id="scope:1",
                  files=(Obj(path=PATH, status=source_status, blob_sha=BLOB),),
                  unresolved=())
    verified = Obj(repository="demo/repo", revision=REV, scope_id="scope:1",
                   status=verification, unverified_properties=("SEMANTIC_COMPATIBILITY_UNPROVEN",))
    return Obj(graph=graph, receipt=receipt, verification=verified)


class HUAdapterTests(unittest.TestCase):
    def test_maps_collector_metrics_without_independent_ast_reimplementation(self):
        result = assess_code_hu(diagnostic(), "n:f")
        self.assertEqual(result.revision, REV)
        self.assertEqual(result.blob_sha, BLOB)
        self.assertEqual(result.structural_metrics[0].name, "loc")
        self.assertEqual(result.structural_metrics[0].evidence_ids, ("ev:decl",))
        self.assertIsNone(result.predicted_score)
        self.assertIn("SEMANTIC_COMPATIBILITY_UNPROVEN", result.unknowns)

    def test_source_bound_human_observation_is_forwarded(self):
        observation = HUObservation("e1", "q1", "INTENT_ACCURACY", True, REV, BLOB)
        result = assess_code_hu(diagnostic(), "n:f", observations=(observation,))
        self.assertEqual(result.observed[0].positive_count, 1)

    def test_invalid_scope_is_rejected(self):
        data = diagnostic()
        data.receipt.revision = "c" * 40
        with self.assertRaisesRegex(ValueError, "HU_ADAPTER_SCOPE_MISMATCH"):
            assess_code_hu(data, "n:f")

    def test_failed_provenance_rejected(self):
        with self.assertRaisesRegex(ValueError, "HU_ADAPTER_PROVENANCE_FAILED"):
            assess_code_hu(diagnostic(verification="FAILED"), "n:f")

    def test_missing_source_rejected(self):
        data = diagnostic()
        data.receipt.files = ()
        with self.assertRaisesRegex(ValueError, "HU_ADAPTER_TARGET_SOURCE_MISSING"):
            assess_code_hu(data, "n:f")

    def test_unknown_target_rejected(self):
        with self.assertRaisesRegex(ValueError, "HU_ADAPTER_UNKNOWN_TARGET"):
            assess_code_hu(diagnostic(), "n:missing")

    def test_incomplete_source_remains_unknown(self):
        result = assess_code_hu(diagnostic(source_status="UNRESOLVED"), "n:f")
        self.assertIn("HU_SOURCE_NOT_SCANNED:UNRESOLVED", result.unknowns)

    def test_missing_metrics_not_filled_with_guessed_scores(self):
        result = assess_code_hu(diagnostic(attributes={}), "n:f")
        self.assertEqual(result.structural_metrics, ())
        self.assertIn("HU_STRUCTURAL_METRICS_UNAVAILABLE", result.unknowns)


if __name__ == "__main__":
    unittest.main()


def test_summary_preserves_structural_measurements_and_unknowns():
    from physics_harness.code.analysis.hu_adapter import summarize_hu
    result = summarize_hu(assess_code_hu(diagnostic(), "n:f"))
    assert result.name == "HU"
    assert result.status == "REVIEW_REQUIRED"
    assert result.source_revision == REV
    assert {v.name: v.value for v in result.values}["structural.branches"] == 1
    assert "HUMAN_UNDERSTANDABILITY_NOT_OBSERVED" in result.unknowns


def test_summary_does_not_forge_population_score_from_single_person():
    from physics_harness.code.analysis.hu_adapter import summarize_hu
    observation = HUObservation("e1", "q1", "INTENT_ACCURACY", True, REV, BLOB)
    result = summarize_hu(assess_code_hu(
        diagnostic(), "n:f", observations=(observation,)
    ))
    assert result.status == "OBSERVED"
    assert not any(v.name.endswith(".positive_rate") for v in result.values)
    assert any(v.name.endswith(".positive_count") for v in result.values)


def test_different_human_criteria_are_not_conflated_by_name():
    from physics_harness.code.analysis.hu_adapter import summarize_hu
    observations = (
        HUObservation("e1", "b.c", "a", True, REV, BLOB),
        HUObservation("e2", "c", "a.b", False, REV, BLOB),
    )
    result = summarize_hu(assess_code_hu(diagnostic(), "n:f", observations=observations))
    assert len(result.values) == 3 + 6  # structural + 3 measurements per distinct question
