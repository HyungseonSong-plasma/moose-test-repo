from __future__ import annotations

import math
from pathlib import Path

from experiments.Issue27_surface_reactions.controlled_wall.positive import (
    BC_O,
    BC_O2P,
    BC_OP,
    FARADAY_C_PER_MOL,
    PLASMA_WALLS,
    _build_a3_case_input,
    _flux_contract,
    _validated_parameters,
)
from qpx_harness.application.experiment_spec import load_experiment_spec
from qpx_harness.adapters.moose import blocks as mb
from qpx_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
R4_SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
A3_SPEC = ROOT / "experiments/Issue27_surface_reactions/A3_positive_ion_neutralization/experiment.json"
EXPECTED_WALLS = (
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)


def _bc_value(text: str, name: str) -> float:
    return float(mp.get_parameter(text, f"FVBCs/{name}", "value") or "nan")


def test_issue27_a3_spec_freezes_positive_ions_with_see_off() -> None:
    spec = load_experiment_spec(A3_SPEC)
    frozen = _validated_parameters(spec.parameters)
    flux = _flux_contract(spec.parameters)

    assert spec.protocol == "issue27-surface-reaction-controlled-wall"
    assert frozen["wall_model"] == "positive_ion_prescribed_control"
    assert frozen["wall_boundaries"] == list(EXPECTED_WALLS)
    assert frozen["excluded_boundaries"] == ["inlet", "outlet"]
    assert frozen["secondary_emission_coefficient"] == 0.0
    assert frozen["electron_compensation"] is False

    r_o2p = float(frozen["O2p_event_flux_mol_m2_s"])
    r_op = float(frozen["Op_event_flux_mol_m2_s"])
    assert math.isclose(
        flux["O2p_plasma_charge_rate_density_C_m2_s"],
        -FARADAY_C_PER_MOL * r_o2p,
        rel_tol=0.0,
        abs_tol=0.0,
    )
    assert math.isclose(
        flux["Op_plasma_charge_rate_density_C_m2_s"],
        -FARADAY_C_PER_MOL * r_op,
        rel_tol=0.0,
        abs_tol=0.0,
    )
    assert flux["O2p_plasma_charge_rate_density_C_m2_s"] < 0.0
    assert flux["Op_plasma_charge_rate_density_C_m2_s"] < 0.0


def test_issue27_a3_o2p_only_uses_six_wall_outward_loss() -> None:
    spec = load_experiment_spec(A3_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    control_text, _ = _build_a3_case_input(
        base,
        parameters=spec.parameters,
        mode="control",
    )
    text, meta = _build_a3_case_input(
        base,
        parameters=spec.parameters,
        mode="o2p_only",
    )

    assert meta["predecessor"]["audit"]["status"] == "PASS"
    assert tuple(PLASMA_WALLS) == EXPECTED_WALLS
    assert meta["frozen_phase"]["secondary_emission"] is False
    assert meta["frozen_phase"]["electron_wall_compensation"] is False

    for name in (BC_O2P, BC_OP, BC_O):
        path = f"FVBCs/{name}"
        assert mp.get_parameter(text, path, "type") == "FVNeumannBC"
        assert tuple(mp.words(mp.get_parameter(text, path, "boundary"))) == EXPECTED_WALLS

    assert _bc_value(control_text, BC_O2P) == 0.0
    assert _bc_value(control_text, BC_OP) == 0.0
    assert _bc_value(control_text, BC_O) == 0.0
    assert _bc_value(text, BC_O2P) < 0.0
    assert _bc_value(text, BC_OP) == 0.0
    assert _bc_value(text, BC_O) == 0.0
    assert not mb.has_block(text, "FVBCs/issue27_electron_wall_absorption")
    assert mp.get_parameter(text, "FVKernels/n_e_drift", "potential") == "potential_plasma"


def test_issue27_a3_op_only_returns_equal_mass_o_without_electron_bc() -> None:
    spec = load_experiment_spec(A3_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_a3_case_input(
        base,
        parameters=spec.parameters,
        mode="op_only",
    )

    op_loss = _bc_value(text, BC_OP)
    o_return = _bc_value(text, BC_O)

    assert meta["predecessor"]["audit"]["status"] == "PASS"
    assert _bc_value(text, BC_O2P) == 0.0
    assert op_loss < 0.0
    assert o_return > 0.0
    assert math.isclose(abs(op_loss), abs(o_return), rel_tol=0.0, abs_tol=0.0)
    assert not mb.has_block(text, "FVBCs/issue27_electron_wall_absorption")
    assert mp.get_parameter(text, "FVKernels/n_e_drift", "potential") == "potential_plasma"
