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


def test_pinned_cue_replay_is_deterministic_and_keeps_unknowns():
    import json
    from experiments.definition_cu_v03.measure_frozen_baseline import run

    path = ROOT / "experiments/definition_cu_v02/pilot_inputs.json"
    baseline = json.loads(path.read_text(encoding="utf-8"))
    out = run(baseline)
    stored = json.loads((ROOT / "experiments/definition_cu_v03/frozen_baseline_measurements.json")
                        .read_text(encoding="utf-8"))
    assert out == stored
    assert [x["metrics"]["MRC_extra_cues"] for x in out["results"] if x["metrics"] is not None].count(None) == 4
    assert out["full_source_ast_scanned"] is False


def test_private_underscore_modules_not_counted_as_default_name_cues(tmp_path):
    from experiments.definition_cu_v03.measure import public_module_cues
    for name in ("_validation.py", "node.py", "__init__.py"):
        (tmp_path / name).write_text("# fixture\n", encoding="utf-8")
    assert public_module_cues(tmp_path) == ("node",)
