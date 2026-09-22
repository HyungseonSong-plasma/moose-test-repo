from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "experiment.yml"


def test_experiment_workflow_routes_from_manifest_cases() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "matrix route" in text
    assert "needs.route.outputs.mode == 'serial'" in text
    assert "needs.route.outputs.mode == 'matrix'" in text
    assert "case_count" in text

    # Matrix eligibility must never be encoded as a historical sequence allowlist.
    for sequence in ("07", "08", "09", "10", "11", "12"):
        assert f"inputs.sequence == '{sequence}'" not in text
        assert f"inputs.sequence != '{sequence}'" not in text


def test_issue306_sequence03_is_declared_matrix() -> None:
    import json

    manifest = json.loads(
        (
            ROOT
            / "automation"
            / "manifests"
            / "experiments"
            / "Issue_306_experiments03.json"
        ).read_text(encoding="utf-8")
    )
    assert len(manifest["cases"]) == 6
    assert manifest["max_parallel"] == 3
    assert "prepare_manifest" in manifest
    assert manifest["aggregate"] is not None
