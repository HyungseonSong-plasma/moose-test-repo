from __future__ import annotations

from pathlib import Path

from qpx_harness.application.experiment_spec import load_experiment_spec
from qpx_harness.adapters.moose import blocks as mb
from qpx_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue26_e1 import ENERGY_VARIABLE
from experiments.historical_recipe_support.issue26_e2a import (
    E2A_DIFFUSION_KERNEL,
    E2A_DIFFUSIVITY_M2_S,
    E2A_IC,
    E2A_INITIAL_FUNCTION,
    build_issue26_e2a_input,
)

ROOT = Path(__file__).resolve().parents[2]
R4_SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
E2A_SPEC = ROOT / "experiments/Issue26_electron_energy/E2a_controlled_diffusion/experiment.json"


def test_issue26_e2a_spec_is_registered_controlled_diffusion() -> None:
    spec = load_experiment_spec(E2A_SPEC)
    assert spec.protocol == "issue26-electron-energy-e2a"
    assert spec.parameters["energy_model"] == "controlled_diffusion"


def test_issue26_e2a_builds_function_ic_and_controlled_diffusion() -> None:
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = build_issue26_e2a_input(
        base,
        diffusivity_m2_s=E2A_DIFFUSIVITY_M2_S,
    )

    assert mb.has_block(text, f"Functions/{E2A_INITIAL_FUNCTION}")
    assert mb.has_block(text, f"ICs/{E2A_IC}")
    assert mb.has_block(text, f"FVKernels/{E2A_DIFFUSION_KERNEL}")
    assert mp.get_parameter(text, f"Variables/{ENERGY_VARIABLE}", "initial_condition") is None
    assert mp.get_parameter(text, f"ICs/{E2A_IC}", "variable") == ENERGY_VARIABLE
    assert mp.get_parameter(text, f"FVKernels/{E2A_DIFFUSION_KERNEL}", "variable") == ENERGY_VARIABLE
    assert (
        mp.get_parameter(text, f"FVKernels/{E2A_DIFFUSION_KERNEL}", "coeff")
        == "electron_energy_diffusivity_control"
    )
    assert meta["diffusivity_m2_s"] == E2A_DIFFUSIVITY_M2_S
    assert meta["energy_diffusion_enabled"] is True
    assert meta["energy_drift_enabled"] is False
    assert meta["joule_source_enabled"] is False
    assert meta["wall_energy_flux_enabled"] is False


def test_issue26_e2a_zero_diffusion_control_keeps_same_structure() -> None:
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = build_issue26_e2a_input(base, diffusivity_m2_s=0.0)

    values = mp.words(
        mp.get_parameter(
            text,
            "FunctorMaterials/e2a_energy_diffusivity",
            "prop_values",
        )
    )
    assert values == ["0"]
    assert mb.has_block(text, f"FVKernels/{E2A_DIFFUSION_KERNEL}")
    assert meta["diffusivity_m2_s"] == 0.0
    assert mp.get_parameter(text, "FunctorMaterials/electron_transport", "mean_energy") == "mean_en"
    assert not mb.has_block(text, "FVKernels/n_epsilon_drift")
