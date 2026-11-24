"""v0.4 exact HEAD Git-object inventory integration, no Physics execution."""
from __future__ import annotations

from pathlib import Path

from experiments.definition_cu_v04.measure import measure_repository, TARGETS

ROOT = Path(__file__).resolve().parents[3]


def test_full_python_source_inventory_and_context_discrimination():
    report = measure_repository(ROOT)
    assert report["schema_version"] == "0.4"
    assert report["readme_used"] is False
    assert report["target_name_used_for_definition_inference"] is False
    assert report["source_provider"] == "GIT_TREE_EXACT_BLOB"
    assert report["semantic_cu_calibrated"] is False
    assert [v["target"] for v in report["results"]] == list(TARGETS)
    assert sum(v["scanned_files"] for v in report["results"]) > 6  # exceeds v0.3 sample
    assert all(v["scanned_files"] == v["tracked_python_files"] for v in report["results"])
    assert all(not v["unknowns"] or "SOURCE_BUDGET_EXCEEDED" not in v["unknowns"]
               for v in report["results"])
    for row in report["results"]:
        assert row["revision"] == report["exact_source_revision"]
        assert row["declared_entities"] >= 0
        assert all(len(w["source_ref"].split("@")[-1]) == 40
                   for w in row["source_evidence"])
        assert all(len(w["source_ref"].split("@")[-1]) == 40
                   for w in row["import_relations"])
        if row["definition"] is None:
            assert row["metrics"] is None
            assert row["name_contrast"] is None
        else:
            assert row["metrics"]["MRC_extra_cues"] is None or row["metrics"]["MRC_extra_cues"] >= 0
            assert row["name_contrast"]["semantic_name_alignment_proven"] is False
