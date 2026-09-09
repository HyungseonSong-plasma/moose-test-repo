from __future__ import annotations

from pathlib import Path

from experiments.Issue27_surface_reactions.controlled_wall.electron_wall import THERMAL_BC
from experiments.Issue27_surface_reactions.controlled_wall.electron_wall_stable import (
    A7_DISCRIMINATOR_DT_S,
    _build_a7_case_input,
)
from physics_harness.application.experiment_spec import load_experiment_spec
from physics_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
R4_SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
A7_SPEC = ROOT / "experiments/Issue27_surface_reactions/A7_comsol_electron_wall/experiment.json"


def test_issue27_a7_stable_wrapper_uses_short_one_step_only() -> None:
    spec = load_experiment_spec(A7_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_a7_case_input(
        base,
        parameters=spec.parameters,
        mode="electron_thermal_only",
    )

    assert A7_DISCRIMINATOR_DT_S == 1.0e-10
    assert float(mp.get_parameter(text, "Executioner", "dt") or "nan") == A7_DISCRIMINATOR_DT_S
    assert float(mp.get_parameter(text, "Executioner", "end_time") or "nan") == A7_DISCRIMINATOR_DT_S
    assert float(mp.get_parameter(text, f"FVBCs/{THERMAL_BC}", "factor") or "nan") == -1.0
    assert meta["a7_discriminator_timestep_s"] == A7_DISCRIMINATOR_DT_S
    assert "thermal wall-flux physics unchanged" in meta["a7_timestep_scope"]
