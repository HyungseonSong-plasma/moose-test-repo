from __future__ import annotations

import csv
from pathlib import Path

from experiments.Issue93_r3_electron_isolation.check import check_csv
from experiments.Issue93_r3_electron_isolation.dependency_audit import audit
from experiments.Issue93_r3_electron_isolation.prepare import (
    DEFAULT_DT,
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
    assert "T_g_IS_AUXILIARY" in deps["dR_e_dT_g"]
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


def test_issue93_j1_generated_case_is_frozen_heavy_real_qvt_reduction() -> None:
    text = build_input(SOURCE_CASE, DEFAULT_DT)
    assert "type = FileMeshGenerator" in text
    assert "file = 'qvt.msh'" in text
    assert "[n_e]" in text
    assert "type = MooseVariableFVReal" in text
    assert "[n_e_time]" in text and "type = FVTimeKernel" in text
    assert "[n_e_diffusion]" in text and "type = FVDiffusion" in text
    assert "[n_e_drift]" in text and "type = QPXFVElectrostaticDrift" in text
    assert "carrier = carrier_one" in text
    assert "advected_interp_method = upwind" in text
    assert "type = QPXElectronTransportLookupMaterial" in text
    assert "property_table_file = electron_moments.txt" in text
    assert "mean_energy = mean_en" in text
    assert "pressure = p_frozen" in text
    assert "gas_temperature = T_g_frozen" in text
    assert "bounds_policy = error" in text
    assert "expression = '0'" in text
    assert "type = QPXThermalDiffusionMaterial" not in text
    assert "type = INSFVPressureVariable" not in text
    assert "type = QPXFVMixtureAveragedDiffusion" not in text
    assert "WCNSFV" not in text
    assert "Poisson" not in text.replace("Poisson is OFF", "")


def test_issue93_prepare_copies_real_assets_and_records_identity(tmp_path: Path) -> None:
    evidence = prepare_case(tmp_path / "j1", SOURCE_CASE, DEFAULT_DT)
    dest = tmp_path / "j1"
    assert (dest / "qvt.msh").is_file()
    assert (dest / "electron_moments.txt").is_file()
    assert (dest / "input.i").is_file()
    assert evidence["heavy_nonlinear_equations"] == "REMOVED_FOR_DIAGNOSTIC"
    assert evidence["poisson"] == "OFF"
    assert evidence["dt_s"] == DEFAULT_DT
    assert len(evidence["mesh_sha256"]) == 64
    assert len(evidence["electron_table_sha256"]) == 64


def test_issue93_checker_accepts_positive_time_uniform_invariant(tmp_path: Path) -> None:
    path = tmp_path / "out.csv"
    fields = [
        "time",
        "n_e_avg",
        "n_e_min",
        "n_e_max",
        "n_e_inventory",
        "carrier_one_integral",
        "electron_mobility_avg",
        "electron_diffusion_avg",
    ]
    volume = 0.125
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for time_value in (0.0, DEFAULT_DT):
            w.writerow(
                {
                    "time": time_value,
                    "n_e_avg": NE_INITIAL,
                    "n_e_min": NE_INITIAL,
                    "n_e_max": NE_INITIAL,
                    "n_e_inventory": NE_INITIAL * volume,
                    "carrier_one_integral": volume,
                    "electron_mobility_avg": 9755.0,
                    "electron_diffusion_avg": 41257.0,
                }
            )
    report = check_csv(path)
    assert report["pass"] is True
    assert report["physical_rows"] == 1
    assert report["inventory_rel_error"] == 0.0


def test_issue93_runtime_parser_reads_only_electron_debug_rows() -> None:
    log = """|residual|_2 of individual variables:
  n_e: 1.25e-1
|residual|_2 of individual variables:
  n_e: 2.5e-3
"""
    assert _electron_residuals(log) == [0.125, 0.0025]
