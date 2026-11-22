"""Real checked-out source P0: behavior identity and bounded source-role gates."""
from __future__ import annotations

from pathlib import Path

from experiments.definition_cu_v03.measure import measure_repository

ROOT = Path(__file__).resolve().parents[3]
EXPECTED = {
    "graph": "GRAPH_MODEL",
    "diagnostics": "SOURCE_FACT_COLLECTION",
    "analysis": "GRAPH_ANALYSIS",
    "refactor": "CHANGE_PLANNING",
    "verification": "SOURCE_VERIFICATION",
    "delete": None,
}


def test_real_python_source_behavior_and_metric_receipts():
    report = measure_repository(ROOT)
    assert report["schema_version"] == "0.3"
    assert report["readme_used"] is False
    assert report["scope_complete_for_whole_folder"] is False
    assert set(row["target"] for row in report["results"]) == set(EXPECTED)
    for row in report["results"]:
        assert row["definition"] == EXPECTED[row["target"]], (row["target"], row["unknowns"])
        assert row["sample_blob"] and len(row["sample_blob"]) == 40
        assert all(item["source_ref"].endswith("@" + row["sample_blob"])
                   for item in row["witnesses"])
        if row["definition"] is None:
            assert row["metrics"] is None
        else:
            assert row["metrics"] is not None
            assert row["metrics"]["DEB_denominator"] == 3
            assert row["metrics"]["MRC_extra_cues"] is None or row["metrics"]["MRC_extra_cues"] >= 0
