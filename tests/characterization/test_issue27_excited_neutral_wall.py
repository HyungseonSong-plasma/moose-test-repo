from __future__ import annotations

import math
from pathlib import Path

from experiments.Issue27_surface_reactions.controlled_wall.excited import (
    O2S_BC,
    OS_BC,
    PLASMA_WALLS,
    _build_a4_case_input,
    _validated_parameters,
)
from qpx_harness.application.experiment_spec import load_experiment_spec
from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
R4_SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
A4_SPEC = ROOT / "experiments/Issue27_surface_reactions/A4_excited_neutral_quenching/experiment.json"
EXPECTED_WALLS = (
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)


def _factor(text: str, name: str) -> float:
    return float(mp.get_parameter(text, f"FVBCs/{name}", "factor") or "nan")


def test_issue27_a4_spec_freezes_excited_neutral_sticking_contract() -> None:
    spec = load_experiment_spec(A4_SPEC)
    frozen = _validated_parameters(spec.parameters)

    assert spec.protocol == "issue27-surface-reaction-controlled-wall"
    assert frozen["wall_model"] == "excited_neutral_sticking_control"
    assert tuple(frozen["wall_boundaries"]) == EXPECTED_WALLS
    assert frozen["excluded_boundaries"] == ["inlet", "outlet"]
    assert frozen["motz_wise_correction"] is False
    assert frozen["gas_temperature_functor"] == "T_g"
    assert math.isclose(float(frozen["O2s_sticking_coefficient"]), 1.0)
    assert math.isclose(float(frozen["Os_sticking_coefficient"]), 0.2)
    assert frozen["secondary_emission"] is False
    assert frozen["electron_compensation"] is False


def test_issue27_a4_o2s_quench_uses_six_wall_state_dependent_loss() -> None:
    spec = load_experiment_spec(A4_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    control_text, _ = _build_a4_case_input(base, parameters=spec.parameters, mode="control")
    text, meta = _build_a4_case_input(base, parameters=spec.parameters, mode="o2s_quench")

    assert meta["predecessor"]["audit"]["status"] == "PASS"
    assert tuple(PLASMA_WALLS) == EXPECTED_WALLS
    assert _factor(control_text, O2S_BC) == 0.0
    assert _factor(control_text, OS_BC) == 0.0
    assert _factor(text, O2S_BC) == -1.0
    assert _factor(text, OS_BC) == 0.0
    assert mp.get_parameter(text, f"FVBCs/{O2S_BC}", "type") == "FVFunctorNeumannBC"
    assert tuple(mp.words(mp.get_parameter(text, f"FVBCs/{O2S_BC}", "boundary"))) == EXPECTED_WALLS
    assert not mb.has_block(text, "FVBCs/issue27_electron_wall_absorption")
    assert mp.get_parameter(text, "FVKernels/n_e_drift", "potential") == "potential_plasma"


def test_issue27_a4_os_quench_is_neutral_and_uses_n_minus_1_o2_return() -> None:
    spec = load_experiment_spec(A4_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_a4_case_input(base, parameters=spec.parameters, mode="os_quench")

    assert meta["predecessor"]["audit"]["status"] == "PASS"
    assert _factor(text, O2S_BC) == 0.0
    assert _factor(text, OS_BC) == -1.0
    assert mp.get_parameter(text, f"FVBCs/{OS_BC}", "type") == "FVFunctorNeumannBC"
    assert tuple(mp.words(mp.get_parameter(text, f"FVBCs/{OS_BC}", "boundary"))) == EXPECTED_WALLS
    assert "Os -> 0.5 constrained O2" in meta["surface_reactions"]["Os"]["reaction"]
    assert "O2 is constrained" in meta["n_minus_1_contract"]
    assert meta["frozen_phase"]["secondary_emission"] is False
    assert meta["frozen_phase"]["electron_wall_compensation"] is False
    assert not mb.has_block(text, "FVBCs/issue27_electron_wall_absorption")
