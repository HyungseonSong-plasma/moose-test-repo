"""Analysis interprets code-understandability measurements without redefining their equations."""

import pytest

from libs.code_lucidity import UnderstandabilityInput, evaluate_understandability, from_python_ast
from physics_harness.code.analysis.adapters.lucidity_interpretation import interpret_understandability_indicators


def test_interpretation_is_contextual_not_a_score_or_change_verdict():
    source = from_python_ast({"loc": 10, "branches": 2}, evidence_ids=("ev:source",))
    hu = evaluate_understandability(UnderstandabilityInput("node:sample", "a" * 40, "b" * 40, source))
    review = interpret_understandability_indicators(hu)
    assert review.status == "REVIEW_REQUIRED"
    assert review.source_revision == "a" * 40
    assert review.evidence_ids == ("ev:source",)
    assert review.values[0].name == "indicator.branch_density"
    assert review.values[0].value == 0.2
    assert "not a count of independent responsibilities" in review.summary
    assert "No metric alone proves" in review.summary


def test_missing_model_indicators_remain_unknown_in_analysis():
    hu = evaluate_understandability(UnderstandabilityInput("node:sample", "a" * 40, "b" * 40))
    review = interpret_understandability_indicators(hu)
    assert not review.values
    assert "No computable code-understandability indicators" in review.summary
    assert "HUMAN_UNDERSTANDABILITY_NOT_OBSERVED" not in review.unknowns


def test_interpretation_rejects_non_hu_values():
    with pytest.raises(TypeError, match="UNDERSTANDABILITY_ASSESSMENT_REQUIRED"):
        interpret_understandability_indicators(object())
