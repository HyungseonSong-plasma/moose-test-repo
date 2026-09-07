from __future__ import annotations

import csv
import math
from pathlib import Path

from experiments.Issue31_r4_qf2_local_charge_relaxation import run as qf2_run
from qpx_harness.adapters.moose import blocks as mb
from qpx_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue31_r4_qf2 import (
    QF2_CHARGE_MAX_PP,
    QF2_CHARGE_MIN_PP,
    QF2_NE_FUNCTION,
    QF2_NE_IC,
    QF2_NE_PERTURBATION_AMPLITUDE,
    QVT_CELL_CENTROID_MAX_ABS_Y_OFFSET_M,
    QVT_RZ_VOLUME_WEIGHTED_Y_MEAN_M,
    audit_r4_qf2_input,
    build_r4_qf2_input,
)

ROOT = Path(__file__).resolve().parents[2]
R3_E0 = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0"


def _base() -> str:
    return (R3_E0 / "heavy_base.i").read_text()


def test_qf2_adds_mean_preserving_electron_local_charge_perturbation() -> None:
    text, meta = build_r4_qf2_input(_base())
    audit = audit_r4_qf2_input(
        text,
        expected_reference_m3=meta["electron_reference_density_m3"],
    )

    assert audit["status"] == "PASS"
    assert meta["predecessor"]["audit"]["status"] == "PASS"
    assert meta["predecessor"]["inlet"]["feed"] == "pure O2"
    assert meta["predecessor"]["inlet"]["flow_sccm"] == 20.0
    assert meta["predecessor"]["initial_plasma"]["neutral_O_spatial_perturbation"] is False

    assert mp.get_parameter(text, "Variables/n_e", "initial_condition") is None
    assert mb.has_block(text, f"Functions/{QF2_NE_FUNCTION}")
    assert mb.has_block(text, f"ICs/{QF2_NE_IC}")
    expression = mp.get_parameter(text, f"Functions/{QF2_NE_FUNCTION}", "expression")
    assert expression is not None
    assert f"{QF2_NE_PERTURBATION_AMPLITUDE:.17g}" in expression
    assert f"{QVT_RZ_VOLUME_WEIGHTED_Y_MEAN_M:.17g}" in expression
    assert f"{QVT_CELL_CENTROID_MAX_ABS_Y_OFFSET_M:.17g}" in expression
    assert mp.get_parameter(text, f"ICs/{QF2_NE_IC}", "variable") == "n_e"
    assert mp.get_parameter(text, f"ICs/{QF2_NE_IC}", "function") == QF2_NE_FUNCTION


def test_qf2_observes_actual_initial_and_final_local_charge() -> None:
    text, _ = build_r4_qf2_input(_base())

    for pp in ("n_e_min", "n_e_max", "n_e_avg", "r31_charge_integral"):
        assert tuple(
            mp.words(mp.get_parameter(text, f"Postprocessors/{pp}", "execute_on"))
        ) == ("INITIAL", "TIMESTEP_END")

    for name, value_type in (
        (QF2_CHARGE_MIN_PP, "min"),
        (QF2_CHARGE_MAX_PP, "max"),
    ):
        path = f"Postprocessors/{name}"
        assert mb.has_block(text, path)
        assert mp.get_parameter(text, path, "functor") == "charge_density"
        assert mp.get_parameter(text, path, "value_type") == value_type
        assert tuple(mp.words(mp.get_parameter(text, path, "execute_on"))) == (
            "INITIAL",
            "TIMESTEP_END",
        )


def test_qf2_relaxation_evidence_accepts_global_neutral_local_relaxation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "input_out.csv"
    reference = 1.0e18
    fieldnames = (
        "time",
        "domain_volume",
        "r31_charge_integral",
        QF2_CHARGE_MIN_PP,
        QF2_CHARGE_MAX_PP,
        "n_e_min",
        "n_e_max",
        "n_e_avg",
    )
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "time": "0",
                "domain_volume": "0",
                "r31_charge_integral": "0",
                QF2_CHARGE_MIN_PP: "-1e-5",
                QF2_CHARGE_MAX_PP: "1e-5",
                "n_e_min": "9.999e17",
                "n_e_max": "1.0001e18",
                "n_e_avg": "1e18",
            }
        )
        writer.writerow(
            {
                "time": "1e-8",
                "domain_volume": "0.05",
                "r31_charge_integral": "1e-18",
                QF2_CHARGE_MIN_PP: "-1e-6",
                QF2_CHARGE_MAX_PP: "1e-6",
                "n_e_min": "9.9999e17",
                "n_e_max": "1.00001e18",
                "n_e_avg": "1e18",
            }
        )

    evidence = qf2_run._local_relaxation_evidence(
        path,
        electron_reference_m3=reference,
        phi_abs_max_V=1.0,
    )
    assert evidence["status"] == "MEASURED"
    assert evidence["initial_volume_charge_C"] == 0.0
    assert evidence["initial_global_carrier_scaled_charge"] == 0.0
    assert evidence["initial_local_charge_density_amplitude_C_per_m3"] == 1.0e-5
    assert evidence["final_local_charge_density_amplitude_C_per_m3"] == 1.0e-6
    assert math.isclose(
        evidence["local_charge_relaxation_ratio"],
        0.1,
        rel_tol=1.0e-15,
        abs_tol=0.0,
    )
    assert evidence["initial_n_e_mean_relative_offset"] == 0.0
    assert evidence["pass"] is True
    assert all(evidence["gates"].values())
