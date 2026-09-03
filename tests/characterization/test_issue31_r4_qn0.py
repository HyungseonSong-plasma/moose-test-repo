from __future__ import annotations

import csv
import json
from pathlib import Path

from experiments.Issue31_r4_qn0_all_ground import run as issue31_qn0_run
from qpx_harness.moose import parameters as mp
from recipes.issue31_r4_qn0 import (
    audit_r4_qn0_input,
    build_r4_qn0_input,
    initial_quasi_neutral_reference,
)

ROOT = Path(__file__).resolve().parents[2]
R3_E0 = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0"


def _base() -> str:
    return (R3_E0 / "heavy_base.i").read_text()


def test_qn_reference_is_reproducible_from_initial_heavy_charge() -> None:
    qn = initial_quasi_neutral_reference(_base())

    assert abs(qn["mixture_molar_mass_kg_per_mol"] - 0.025806451612903226) < 1e-16
    assert abs(qn["initial_density_kg_per_m3"] - 6.896755255172883e-06) < 1e-18
    assert abs(qn["electron_reference_density_m3"] - 1.2979134666850255e18) < 1e5
    assert qn["initial_charge_number_closure_m3"] == 0.0


def test_r4_qn0_preserves_normalized_representation_and_q0_contract() -> None:
    text, meta = build_r4_qn0_input(_base())
    audit = audit_r4_qn0_input(text)

    assert audit["status"] == "PASS"
    assert meta["poisson_enabled"] is True
    assert meta["electrostatic_feedback_enabled"] is False
    assert meta["surface_accumulated_charge_enabled"] is False
    assert meta["electron_solver_unknown"] == "n_e == n_hat"
    assert meta["electron_initial_condition"] == "normalized_1.0"
    assert mp.get_parameter(text, "Variables/n_e", "initial_condition") == "1.0"
    assert (
        mp.get_parameter(
            text,
            "FunctorMaterials/electron_density_physical",
            "expression",
        )
        == "'${n_e_value}*ne_hat'"
    )
    assert mp.get_parameter(text, "FVKernels/n_e_drift", "potential") == "phi_prescribed"
    assert meta["reference_density_ratio_to_r3"] > 100.0


def test_qn0_stage_retargets_r3_checker_to_quasi_neutral_reference(tmp_path: Path) -> None:
    target = tmp_path / "R4_QN0"
    staged = issue31_qn0_run._stage(target)

    reference = staged["construction"]["quasi_neutral_reference"][
        "electron_reference_density_m3"
    ]
    expected = json.loads((target / "expected.json").read_text())
    assert expected["field_strength"] == 0.0
    assert expected["n0"] == reference
    assert staged["construction"]["audit"]["status"] == "PASS"
    assert (target / "input.i").is_file()


def test_qn0_state_evidence_is_measurement_only(tmp_path: Path) -> None:
    path = tmp_path / "input_out.physical.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "time",
                "domain_volume",
                "n_e_avg",
                "n_e_min",
                "n_e_max",
                "r31_charge_integral",
                "r31_phi_min",
                "r31_phi_max",
            ),
        )
        writer.writeheader()
        writer.writerow(
            {
                "time": "1e-8",
                "domain_volume": "0.05",
                "n_e_avg": "1.3e18",
                "n_e_min": "1.29e18",
                "n_e_max": "1.31e18",
                "r31_charge_integral": "1e-6",
                "r31_phi_min": "-2",
                "r31_phi_max": "3",
            }
        )

    evidence = issue31_qn0_run._state_evidence(path)
    assert evidence["status"] == "MEASURED"
    assert evidence["average_charge_density_C_per_m3"] == 2e-5
    assert evidence["phi_span_V"] == 5.0
    assert evidence["phi_abs_max_V"] == 3.0
    assert evidence["acceptance"] == "UNSET_QN0_CONTROL_MEASUREMENT"
