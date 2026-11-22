"""v0.4 exact HEAD Git-object inventory integration, no Physics execution."""
from __future__ import annotations

import json
import os
from pathlib import Path
import warnings

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

    # Pilot-only machine receipt in the standard pytest warning summary. It
    # must not be interpreted as a human-CU or full-repository coverage verdict.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        snapshot = [{"target": r["target"],
                     "files": r["scanned_files"],
                     "role": r["definition"],
                     "candidates": r["candidates"],
                     "DEB": r["metrics"]["DEB"] if r["metrics"] else None,
                     "MRC": r["metrics"]["MRC_extra_cues"] if r["metrics"] else None,
                     "name_discrimination": r["name_contrast"]["result"] if r["name_contrast"] else None}
                    for r in report["results"]]
        warnings.warn("DEFINITION_CU_V04_PILOT=" + json.dumps(snapshot, separators=(",", ":")),
                      UserWarning, stacklevel=1)
