import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "experiments" / "Issue310_fp_acceleration" / "qualified_baseline.json"


def test_issue310_qualified_baseline_contract():
    data = json.loads(BASELINE.read_text())

    assert data["issue"] == 310
    assert data["status"] == "PERFORMANCE_CONFIGURATION_QUALIFIED"
    assert data["canonical_source"]["branch"] == "qualified/issue310-gummel-optimized"
    assert data["canonical_source"]["sha"] == "cdba1cba025da3c8442c0ad2993aeccab0111732"
    assert data["canonical_source"]["case"] == "optimized_endpoint_20ns"

    coupling = data["coupling_defaults"]
    assert coupling["bandwidth"] == 5
    assert coupling["relaxation_factor"] == 0.45
    assert coupling["fixed_point_algorithm"] == "steffensen"
    assert coupling["delta_phi_abs_tol_V"] == 1.0e-6
    assert coupling["compute_scaling_once"] is True

    output = data["output_defaults"]
    assert output["fp_anchor_csv_enabled"] is False
    assert output["vector_profiles"] == "FINAL_ONLY"

    q = data["qualification"]
    assert q["workflow_run"] == 36051947264
    assert q["geometric_mean_speedup"] > 12.0
    assert q["wall_time_reduction_fraction"] > 0.91
    assert q["optimized_fixed_point_per_electron_step"] < 30.0
    assert q["fixed_point_reduction_fraction"] > 0.93

    assert data["use_policy"]["default_for_future_gummel_performance_work"] is True
    assert data["use_policy"]["historical_relax2x_reference_is_default"] is False
