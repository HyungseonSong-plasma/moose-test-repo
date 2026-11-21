"""Independent HU library: counts are not an invented understandability score."""

import unittest
from dataclasses import replace

from libs.hu import (
    HUInput, HUObservation, StructuralMetric, compare_hu, evaluate_hu,
    from_python_ast,
)

REV = "a" * 40
BLOB = "b" * 40


def observation(evaluator="person-1", *, good=True, revision=REV,
                question="source-intent", criterion="INTENT_ACCURACY"):
    return HUObservation(evaluator, question, criterion, good, revision, BLOB)


def sample(*, observations=(), attributes=None, unknowns=()):
    attrs = {"loc": 20, "branches": 3, "max_branch_nesting": 2} if attributes is None else attributes
    return HUInput("node:func", REV, BLOB, from_python_ast(attrs, evidence_ids=("ev:x",)),
                   observations, unknowns)


class HULibraryTests(unittest.TestCase):
    def test_structure_is_descriptive_and_no_predicted_score(self):
        result = evaluate_hu(sample())
        self.assertEqual([m.name for m in result.structural_metrics],
                         ["loc", "branches", "max_branch_nesting"])
        self.assertIsNone(result.predicted_score)
        self.assertFalse(result.observed)
        self.assertIn("HUMAN_UNDERSTANDABILITY_NOT_OBSERVED", result.unknowns)

    def test_external_score_attribute_is_not_accepted_as_hu_evidence(self):
        result = evaluate_hu(sample(attributes={"loc": 12, "hu_score": 100}))
        self.assertEqual([x.name for x in result.structural_metrics], ["loc"])

    def test_one_evaluator_is_binary_observation_not_percentage(self):
        hu = evaluate_hu(sample(observations=(observation(),)))
        self.assertEqual(hu.observed[0].positive_count, 1)
        self.assertIsNone(hu.observed[0].positive_rate)

    def test_two_independent_evaluators_have_observed_fraction_only(self):
        hu = evaluate_hu(sample(observations=(observation(),
                                                    observation("person-2", good=False))))
        self.assertEqual(hu.observed[0].positive_rate, .5)
        self.assertEqual(hu.observed[0].independent_evaluators, 2)
        self.assertIsNone(hu.predicted_score)

    def test_different_questions_are_never_pooled(self):
        hu = evaluate_hu(sample(observations=(
            observation(question="q1"), observation("person-2", question="q2"),
        )))
        self.assertEqual(len(hu.observed), 2)
        self.assertTrue(all(item.positive_rate is None for item in hu.observed))

    def test_duplicate_evaluator_for_same_question_is_invalid(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_HU_EVALUATOR"):
            evaluate_hu(sample(observations=(observation(), observation())))

    def test_wrong_revision_rating_is_invalid(self):
        with self.assertRaisesRegex(ValueError, "HU_OBSERVATION_SOURCE_MISMATCH"):
            sample(observations=(observation(revision="c" * 40),))

    def test_nonfinite_and_negative_metrics_are_invalid(self):
        for value in (-1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                StructuralMetric("branches", value, "python_ast")

    def test_comparison_is_descriptive_not_improvement_proof(self):
        left = evaluate_hu(sample())
        right = evaluate_hu(sample(attributes={"loc": 16, "branches": 1,
                                                     "max_branch_nesting": 1}))
        diff = compare_hu(left, right)
        self.assertFalse(diff.improvement_proven)
        self.assertIn("STRUCTURAL_DELTA_NOT_HU_IMPROVEMENT_PROOF", diff.unknowns)
        self.assertEqual({x.name: x.difference for x in diff.metric_differences},
                         {"loc": -4, "branches": -2, "max_branch_nesting": -1})

    def test_comparison_different_target_refuses(self):
        with self.assertRaisesRegex(ValueError, "HU_TARGET_MISMATCH"):
            compare_hu(evaluate_hu(sample()),
                       evaluate_hu(replace(sample(), target_id="other")))

    def test_unmatched_metric_is_reported_without_fabricating_change(self):
        left = evaluate_hu(sample(attributes={"loc": 10, "branches": 2}))
        right = evaluate_hu(sample(attributes={"loc": 11}))
        diff = compare_hu(left, right)
        self.assertEqual([(m.name, m.difference) for m in diff.metric_differences],
                         [("loc", 1)])
        self.assertIn("INCOMPARABLE_HU_METRIC:branches", diff.unknowns)
        self.assertFalse(diff.improvement_proven)

    def test_different_metric_methods_remain_uncomparable(self):
        left = evaluate_hu(sample(attributes={"loc": 10}))
        right = evaluate_hu(replace(sample(attributes={"loc": 11}),
                         structural_metrics=(StructuralMetric("loc", 11, "other"),)))
        diff = compare_hu(left, right)
        self.assertFalse(diff.metric_differences)
        self.assertIn("INCOMPARABLE_HU_METRIC:loc", diff.unknowns)


if __name__ == "__main__":
    unittest.main()
