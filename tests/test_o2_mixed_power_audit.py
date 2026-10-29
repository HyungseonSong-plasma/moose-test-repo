"""Synthetic fail-closed P5 regression for O3P/O1D mixed dissociation."""
import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "experiments/Issue395_powered_chemistry_ladder/analyze_ground_state_power_scan.py"
spec = importlib.util.spec_from_file_location("mixed_diss_audit", SRC)
assert spec and spec.loader
analyzer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyzer)


def fixture(tmp_path: Path, *, excited_mass: float = 0.032, omit: str = "") -> Path:
    result = tmp_path / "case"
    (result / "run").mkdir(parents=True)
    (result / "d1_native").mkdir()
    row = {
        "time": 1e-4,
        "mixed_R_integral": 2.0,
        "mixed_energy_sink_integral": -16.8,
        "mixed_o3p_mass_integral": 0.032,
        "mixed_o1d_mass_integral": excited_mass,
        "mixed_oxygen_molecular_sink_integral": -0.064,
        "mixed_heavy_mass_closure_integral": 0.0,
        "rf_drive_scale_t6": 1.3,
        "P_rf_scaled_W_t6": 400.0,
        "P_abs_maxwell_t6": 400.0,
    }
    if omit:
        del row[omit]
    with (result / "run" / "plasma.csv").open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    (result / "d1_native" / "d1_native_summary.json").write_text(json.dumps({
        "status": "D1_NATIVE_DIAGNOSTIC_INTEGRITY_PASS",
        "wafer_faces": 27, "native_points": 461, "final_time_us": 100.0,
    }))
    return result


def test_positive_mixed_p5_passes_synthetic_equations(tmp_path: Path):
    report = analyzer.audit(fixture(tmp_path), 400, "exact", "success", "success", "mixed")
    assert report["status"] == "PASS"
    assert report["model"] == "O2_mixed_O3P_plus_O1D"
    assert report["science_status"] == "HOLD_CROSS_SECTION_EEPF_QUENCHING"
    assert report["checks"]["dissociation_sources"]["atomic_O1D_mass_source_kg_s_integral"] == 0.032


def test_wrong_O1D_stoichiometry_is_not_pass(tmp_path: Path):
    report = analyzer.audit(fixture(tmp_path, excited_mass=0.064), 400, "exact", "success", "success", "mixed")
    assert report["status"] == "NOT_PASS"
    assert report["checks"]["dissociation_sources"]["status"] == "FAIL"


def test_missing_mixed_observation_is_not_pass(tmp_path: Path):
    report = analyzer.audit(fixture(tmp_path, omit="mixed_o1d_mass_integral"),
                            400, "exact", "success", "success", "mixed")
    assert report["status"] == "NOT_PASS"
    assert "mixed_o1d_mass_integral" in report["checks"]["dissociation_sources"]["missing_columns"]


def test_wrong_ground_channel_cannot_masquerade_as_mixed(tmp_path: Path):
    report = analyzer.audit(fixture(tmp_path), 400, "exact", "success", "success", "ground")
    assert report["status"] == "NOT_PASS"
