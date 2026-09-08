from __future__ import annotations

import csv
import json
from pathlib import Path

from experiments.Issue93_r3_electron_isolation.operator_decomposition import (
    CASE_ORDER,
    _check_accepted_qvt_csv,
    build_case_input,
    classify_first_failure,
    prepare_batch,
)
from experiments.Issue93_r3_electron_isolation.prepare import (
    ELECTRON_REFERENCE_CASE,
    EXPECTED_MESH_SHA256,
    SOURCE_CASE,
)

KB = 1.380649e-23


def test_issue93_j2_case_inputs_are_exact_operator_derivatives() -> None:
    reference = (ELECTRON_REFERENCE_CASE / "input.i").read_text()
    cases = {case_id: build_case_input(case_id, ELECTRON_REFERENCE_CASE) for case_id in CASE_ORDER}

    assert cases["C0"] == reference
    for case_id in ("C1", "C2", "C3", "C4"):
        assert "expression = '0.0*x'" in cases[case_id]
        assert "expression = '-0.01*x'" not in cases[case_id]
        assert "dt = 1e-8" in cases[case_id]
        assert "end_time = 2e-8" in cases[case_id]
        assert "prop_values = '5.73276 1.33322 600.0 1.0'" in cases[case_id]
        assert "property_table_file = electron_moments.txt" in cases[case_id]

    assert "type = FVDiffusion" not in cases["C1"]
    assert "type = QPXFVElectrostaticDrift" not in cases["C1"]

    assert "type = FVDiffusion" in cases["C2"]
    assert "type = QPXFVElectrostaticDrift" not in cases["C2"]

    assert "type = FVDiffusion" not in cases["C3"]
    assert "type = QPXFVElectrostaticDrift" in cases["C3"]

    assert "type = FVDiffusion" in cases["C4"]
    assert "type = QPXFVElectrostaticDrift" in cases["C4"]


def test_issue93_j2_prepare_batch_preserves_real_qvt_identity(tmp_path: Path) -> None:
    manifest = prepare_batch(tmp_path / "j2", SOURCE_CASE, ELECTRON_REFERENCE_CASE)
    assert manifest["qpx_executed"] is False
    assert manifest["scientific_evr_consumed"] == 0
    assert manifest["case_order"] == list(CASE_ORDER)
    assert manifest["identity"]["mesh_sha256"] == EXPECTED_MESH_SHA256
    assert manifest["cases"]["C0"]["identical_to_control_input"] is True
    for case_id in ("C1", "C2", "C3", "C4"):
        assert manifest["cases"][case_id]["identical_to_control_input"] is False
        case_dir = Path(manifest["cases"][case_id]["case_dir"])
        assert (case_dir / "input.i").is_file()
        assert (case_dir / "qvt.msh").is_file()
        assert (case_dir / "electron_moments.txt").is_file()
        assert (case_dir / "expected.json").is_file()


def test_issue93_j2_decision_tree_maps_first_failure() -> None:
    expected = {
        "C0": ("E4_CURRENT_EXECUTABLE_CONTROL_REGRESSION_FAVORED", "E4_CURRENT_EXECUTABLE_CONTROL"),
        "C1": ("E3_TRANSIENT_OR_RUNTIME_REPRESENTATION_FAVORED", "E3_TRANSIENT_OR_RUNTIME"),
        "C2": ("E2_DIFFUSION_OR_FV_BOUNDARY_PATH_FAVORED", "E2_DIFFUSION_OR_FV_BOUNDARY"),
        "C3": ("E1_ZERO_FIELD_DRIFT_PATH_FAVORED", "E1_ZERO_FIELD_DRIFT"),
        "C4": ("E6_ELECTRON_OPERATOR_INTERACTION_FAVORED", "E6_ELECTRON_OPERATOR_INTERACTION"),
    }
    for case_id, (decision_expected, favored_key) in expected.items():
        decision, hypotheses = classify_first_failure(case_id)
        assert decision == decision_expected
        assert hypotheses[favored_key] == "FAVORED"
        assert hypotheses["E5_HEAVY_ELECTRON_COUPLING_NECESSARY"] == "DISFAVORED_BY_J1"

    decision, hypotheses = classify_first_failure(None)
    assert decision == "J2_ALL_OPERATOR_CASES_SUPPORTED_J1_REPEATABILITY_HOLD"
    assert all(value != "FAVORED" for value in hypotheses.values())


def test_issue93_j2_checker_uses_accepted_issue2_qvt_contract(tmp_path: Path) -> None:
    expected = json.loads((ELECTRON_REFERENCE_CASE / "expected.json").read_text())
    neutral = expected["p"] / (KB * expected["T"])
    mobility = expected["muN"] / neutral
    diffusion = expected["DN"] / neutral
    volume = 0.125

    csv_path = tmp_path / "input_out.csv"
    fields = [
        "time",
        "n_avg",
        "n_min",
        "n_max",
        "inventory",
        "domain_volume",
        "neutral_number_density_avg",
        "electron_mobility_avg",
        "electron_diffusion_avg",
    ]
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "time": 0.0,
                "n_avg": expected["n0"],
                "n_min": expected["n0"],
                "n_max": expected["n0"],
                "inventory": expected["n0"] * volume,
                "domain_volume": volume,
                "neutral_number_density_avg": neutral,
                "electron_mobility_avg": mobility,
                "electron_diffusion_avg": diffusion,
            }
        )
        writer.writerow(
            {
                "time": 1.0e-8,
                "n_avg": expected["n0"],
                "n_min": expected["n0"],
                "n_max": expected["n0"],
                "inventory": expected["n0"] * volume,
                "domain_volume": volume,
                "neutral_number_density_avg": neutral,
                "electron_mobility_avg": mobility,
                "electron_diffusion_avg": diffusion,
            }
        )

    report = _check_accepted_qvt_csv(csv_path, ELECTRON_REFERENCE_CASE / "expected.json")
    assert report["pass"] is True
    assert report["physical_rows"] == 1
    assert report["contract"] == "ACCEPTED_ISSUE2_QVT_PREPOISSON"
