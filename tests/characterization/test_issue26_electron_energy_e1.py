from __future__ import annotations

import math
from pathlib import Path

from qpx_harness.application.experiment_spec import load_experiment_spec
from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp
from experiments.historical_recipe_support.issue26_e1 import (
    E1_DT_S,
    ENERGY_REFERENCE_EV,
    ENERGY_TIME_KERNEL,
    ENERGY_VARIABLE,
    MEAN_EN_SOLVED_FUNCTOR,
    build_issue26_e1_input,
)

ROOT = Path(__file__).resolve().parents[2]
R4_SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
E1_SPEC = ROOT / "experiments/Issue26_electron_energy/E1_zero_source/experiment.json"


def test_issue26_e1_spec_is_registered_zero_source_control() -> None:
    spec = load_experiment_spec(E1_SPEC)
    assert spec.protocol == "issue26-electron-energy-e1"
    assert spec.parameters["energy_model"] == "normalized_zero_source"


def test_issue26_e1_builds_normalized_solved_energy_state_without_transport() -> None:
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = build_issue26_e1_input(base, initial_energy_hat=1.0)

    assert mb.has_block(text, f"Variables/{ENERGY_VARIABLE}")
    assert mb.has_block(text, f"FVKernels/{ENERGY_TIME_KERNEL}")
    assert mp.get_parameter(text, f"Variables/{ENERGY_VARIABLE}", "initial_condition") == "1"
    assert mp.get_parameter(text, f"FVKernels/{ENERGY_TIME_KERNEL}", "variable") == ENERGY_VARIABLE
    assert not mb.has_block(text, "FVKernels/n_epsilon_diffusion")
    assert not mb.has_block(text, "FVKernels/n_epsilon_drift")
    assert float(mp.get_parameter(text, "Executioner", "dt") or "nan") == E1_DT_S
    assert float(mp.get_parameter(text, "Executioner", "end_time") or "nan") == E1_DT_S
    assert meta["transport_lookup_coupled_to_solved_energy"] is False
    assert meta["energy_transport_enabled"] is False
    assert meta["joule_source_enabled"] is False
    assert meta["wall_energy_flux_enabled"] is False


def test_issue26_e1_mean_energy_bridge_uses_both_solved_states_but_lookup_stays_fixed() -> None:
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = build_issue26_e1_input(base, initial_energy_hat=0.5)

    assert mp.words(
        mp.get_parameter(
            text,
            f"FunctorMaterials/{MEAN_EN_SOLVED_FUNCTOR}",
            "functor_names",
        )
    ) == [ENERGY_VARIABLE, "n_e"]
    expression = mp.get_parameter(
        text,
        f"FunctorMaterials/{MEAN_EN_SOLVED_FUNCTOR}",
        "expression",
    )
    assert expression is not None
    assert "eps_hat/ne_hat" in expression
    assert mp.get_parameter(text, "FunctorMaterials/electron_transport", "mean_energy") == "mean_en"
    assert math.isclose(
        meta["initial_mean_energy_eV_if_ne_hat_1"],
        0.5 * ENERGY_REFERENCE_EV,
        rel_tol=0.0,
        abs_tol=0.0,
    )
    assert meta["solved_mean_energy"] == (
        "mean_en_solved = energy_reference_eV * n_epsilon_hat / n_e_hat"
    )
