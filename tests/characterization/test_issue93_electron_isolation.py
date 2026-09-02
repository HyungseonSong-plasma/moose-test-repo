from __future__ import annotations

import csv
from pathlib import Path

from experiments.Issue93_r3_electron_isolation.check import check_csv
from experiments.Issue93_r3_electron_isolation.dependency_audit import audit
from experiments.Issue93_r3_electron_isolation.prepare import (
    DEFAULT_DT,
    ELECTRON_REFERENCE_CASE,
    EXPECTED_MESH_SHA256,
    NE_INITIAL,
    SOURCE_CASE,
    build_input,
    prepare_case,
)
from experiments.Issue93_r3_electron_isolation.run import _electron_residuals


def test_issue93_j0_real_r3_dependency_contract() -> None:
    report = audit(SOURCE_CASE)
    assert report["status"] == "J0_COMPLETE"
    assert report["qpx_executed"] is False
    assert report["scientific_evr_consumed"] == 0
    deps = report["newton_dependency_classification"]
    assert deps["dR_e_dn_e"] == "NONZERO_SELF_BLOCK"
    assert "STRUCTURAL_NONLINEAR_CROSS_BLOCK" in deps["dR_e_dp"]
    assert "T_g_IS_CONSTANT_FUNCTOR" in deps["dR_e_dT_g"]
    assert report["coefficient_ownership"]["T_g"] == "CONSTANT_AD_FUNCTOR_MATERIAL_PROPERTY"
    assert "PRESCRIBED_FUNCTION" in deps["dR_e_dphi"]
    owners = {item["object"]: item for item in report["electron_residual_owners"]}
    assert owners["n_e_drift"]["carrier"] == "carrier_one"
    assert report["electron_lookup"]["table"] == "electron_moments.txt"
    assert report["electron_lookup"]["bounds_policy"] == "error"
    reciprocal = report["reciprocal_heavy_dependencies"]
    assert [d["residual_variable"] for d in reciprocal] == [
        "w_O2s",
        "w_O2p",
        "w_O",
        "w_Om",
        "w_Op",
        "w_Os",
    ]
    assert report["explicit_electron_fvbc_objects_present"] is False


def test_issue93_j1_is_one_diff_from_accepted_issue2_qvt_reference() -> None:
    reference = (ELECTRON_REFERENCE_CASE / "input.i").read_text()
    text = build_input(ELECTRON_REFERENCE_CASE, DEFAULT_DT)
    assert "# Issue #93 J1: direct derivative" in text
    assert "expression = '0.0*x'" in text
    assert "expression = '-0.01*x'" not in text
    assert reference.count("expression = '-0.01*x'") == 1

    # Exact accepted framework contract is retained rather than reconstructed.
    for snippet in (
        "[Materials]",
        "prop_names = 'mean_en p_abs T_g carrier_one'",
        "prop_values = '5.73276 1.33322 600.0 1.0'",
        "property_table_file = electron_moments.txt",
        "mean_energy = mean_en",
        "pressure = p_abs",
        "gas_temperature = T_g",
        "bounds_policy = error",
        "carrier = carrier_one",
        "advected_interp_method = upwind",
        "dt = 1e-8",
        "end_time = 2e-8",
        "compute_scaling_once = true",
        "petsc_options_value = 'lu'",
    ):
        assert snippet in text

    assert "type = QPXThermalDiffusionMaterial" not in text
    assert "type = INSFVPressureVariable" not in text
    assert "type = QPXFVMixtureAveragedDiffusion" not in text
    assert "WCNSFV" not in text


def test_issue93_prepare_proves_issue2_issue91_asset_identity(tmp_path: Path) -> None:
    evidence = prepare_case(tmp_path / "j1", SOURCE_CASE, DEFAULT_DT, ELECTRON_REFERENCE_CASE)
    dest = tmp_path / "j1"
    assert (dest / "qvt.msh").is_file()
    assert (dest / "electron_moments.txt").is_file()
    assert (dest / "input.i").is_file()
    assert evidence["heavy_nonlinear_equations"] == "ABSENT_IN_ACCEPTED_ISSUE2_REFERENCE"
    assert evidence["poisson"] == "OFF"
    assert evidence["dt_s"] == DEFAULT_DT
    assert evidence["accepted_reference_end_time_s"] == 2.0e-8
    assert evidence["semantic_diff_count"] == 1
    assert evidence["mesh_sha256"] == EXPECTED_MESH_SHA256
    assert len(evidence["electron_table_sha256"]) == 64
    assert evidence["reference_input_sha256"] != evidence["candidate_input_sha256"]


def test_issue93_checker_accepts_positive_time_uniform_invariant(tmp_path: Path) -> None:
    path = tmp_path / "out.csv"
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
    volume = 0.125
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for time_value in (0.0, DEFAULT_DT, 2.0 * DEFAULT_DT):
            w.writerow(
                {
                    "time": time_value,
                    "n_avg": NE_INITIAL,
                    "n_min": NE_INITIAL,
                    "n_max": NE_INITIAL,
                    "inventory": NE_INITIAL * volume,
                    "domain_volume": volume,
                    "neutral_number_density_avg": 1.609e20,
                    "electron_mobility_avg": 9755.0,
                    "electron_diffusion_avg": 41257.0,
                }
            )
    report = check_csv(path)
    assert report["pass"] is True
    assert report["physical_rows"] == 2
    assert report["inventory_rel_error"] == 0.0
    assert report["observable_contract"] == "ACCEPTED_ISSUE2_QVT_PREPOISSON"


def test_issue93_runtime_parser_prefers_explicit_electron_debug_rows() -> None:
    log = """0 SNES Function norm 9.0e-1
|residual|_2 of individual variables:
  n_e: 1.25e-1
|residual|_2 of individual variables:
  n_e: 2.5e-3
"""
    assert _electron_residuals(log) == [0.125, 0.0025]


def test_issue93_runtime_parser_uses_snes_norm_for_single_variable_case() -> None:
    log = """0 SNES Function norm 9.0e-1
1 SNES Function norm 2.0e-4
"""
    assert _electron_residuals(log) == [0.9, 0.0002]
