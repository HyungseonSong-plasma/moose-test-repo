"""Full-checkout v0.5 source-proxy benchmark; no human CU verdict/mutation."""
from __future__ import annotations

from pathlib import Path

from experiments.definition_cu_v05.measure import measure_repository, ONTOLOGY_VERSION

ROOT = Path(__file__).resolve().parents[3]


def test_contextual_discrimination_uses_exact_source_and_synthetic_negative_controls():
    report = measure_repository(ROOT)
    assert report["schema_version"] == "0.5"
    assert report["source_provider"] == "GIT_TREE_EXACT_BLOB"
    assert report["source_files"] >= 37
    assert report["source_revision"] and len(report["source_revision"]) == 40
    assert report["ontology_version"] == ONTOLOGY_VERSION
    assert report["reference_definitions"] == 5
    assert report["synthetic_contrast_definitions"] == 5
    assert report["candidate_count"] == 10
    assert report["metrics"]["eligible_cases"] == 5
    assert not report["human_cu_calibrated"]
    assert not report["automatic_change_authorized"]
    assert report["name_readme_used_in_definition_inference"] is False
    assert {c["target"] for c in report["cases"]} == {
        "graph", "diagnostics", "analysis", "refactor", "verification", "delete",
    }
    unresolved = next(c for c in report["cases"] if c["target"] == "delete")
    assert unresolved["assessment"] is None
    for item in report["cases"]:
        if item["assessment"] is None:
            continue
        assert item["status"] in {"DISTINCT", "AMBIGUOUS", "WRONG", "ABSTAIN"}
        assert not item["assessment"]["human_cu_calibrated"]
        assert item["counterfactual_names"]["source_role_invariant"] is True
        assert item["assessment"]["source_reference"].startswith(
            "physics_harness/code/" + item["target"] + "/")
        assert len(item["assessment"]["decisions"]) == 4
        for facet in item["source_facets"]:
            assert all("@" in witness for witness in facet["evidence_ids"])
        # If no distinguishing match, don't convert failure into a numeric CU score.
        if item["status"] in {"AMBIGUOUS", "ABSTAIN"}:
            assert item["assessment"]["final_correct"] is False


def test_v05_does_not_change_source_reference_when_swapping_label():
    report = measure_repository(ROOT)
    assert all(x["counterfactual_names"]["source_role_invariant"] for x in report["cases"]
               if x["assessment"] is not None)


def test_frozen_source_anchored_contrast_replay_is_exact():
    import json
    from experiments.definition_cu_v05.replay_frozen import replay

    base = ROOT / "experiments/definition_cu_v05"
    snapshot = json.loads((base / "frozen_reference_cues.json").read_text(encoding="utf-8"))
    expected = json.loads((base / "frozen_measurements.json").read_text(encoding="utf-8"))
    result = replay(snapshot)
    assert result == expected
    assert result["full_source_reparsed"] is False
    assert result["metrics"]["DDA_source_reference_proxy_name_only"] == 0.0
    assert result["metrics"]["DDA_source_reference_proxy_full_context"] == 0.6
    graph = next(c for c in result["cases"] if c["target"] == "graph")
    analysis = next(c for c in result["cases"] if c["target"] == "analysis")
    assert graph["status"] == "DISTINCT"
    assert graph["assessment"]["minimum_extra_cues"] == 1
    assert analysis["status"] == "AMBIGUOUS"
    assert analysis["assessment"]["minimum_correct_tier"] == 2
    assert analysis["assessment"]["stable_correct_tier"] is None
