from __future__ import annotations

from pathlib import Path

from qpx_harness.application.experiment_spec import load_experiment_spec
from qpx_harness.adapters.moose import blocks as mb
from qpx_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue26_e1 import ENERGY_VARIABLE
from experiments.historical_recipe_support.issue26_energy_chain import (
    E2B_DRIFT_KERNEL,
    E2B_FIELD_V_M,
    E2B_LEFT_PP,
    E2B_MOBILITY_M2_V_S,
    E2B_RIGHT_PP,
    E3_FIELD_V_M,
    E3_JOULE_KERNEL,
    E3_MOBILITY_M2_V_S,
    ENERGY_WALL_THERMAL_BC,
    ENERGY_WALL_THERMAL_POWER_PP,
    SEE_ENERGY_BC,
    SEE_ENERGY_COUPLED_POWER_PP,
    build_e2b_drift_input,
    build_e3_joule_input,
    build_e4_e5_wall_input,
)

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
SPEC = ROOT / "experiments/Issue26_electron_energy/E2b_E5_chain/experiment.json"


def test_issue26_energy_chain_spec_is_registered() -> None:
    spec = load_experiment_spec(SPEC)
    assert spec.protocol == "issue26-electron-energy-chain"
    assert spec.parameters["energy_chain"] == "e2b_to_e5_controlled"
    assert spec.parameters["secondary_electron_mean_energy_eV"] == 4.0


def test_e2b_builds_signed_closed_boundary_energy_drift() -> None:
    base = BASE.read_text(encoding="utf-8")
    plus, meta_plus = build_e2b_drift_input(
        base,
        field_v_m=E2B_FIELD_V_M,
        mobility_m2_v_s=E2B_MOBILITY_M2_V_S,
    )
    minus, meta_minus = build_e2b_drift_input(
        base,
        field_v_m=-E2B_FIELD_V_M,
        mobility_m2_v_s=E2B_MOBILITY_M2_V_S,
    )

    assert mb.has_block(plus, f"FVKernels/{E2B_DRIFT_KERNEL}")
    assert mp.get_parameter(plus, f"FVKernels/{E2B_DRIFT_KERNEL}", "variable") == ENERGY_VARIABLE
    assert mp.get_parameter(plus, f"FVKernels/{E2B_DRIFT_KERNEL}", "charge_number") == "-1"
    assert "inlet outlet plasma_electrode" in (
        mp.get_parameter(plus, f"FVKernels/{E2B_DRIFT_KERNEL}", "boundaries_to_avoid") or ""
    )
    assert mb.has_block(plus, f"Postprocessors/{E2B_LEFT_PP}")
    assert mb.has_block(plus, f"Postprocessors/{E2B_RIGHT_PP}")
    assert meta_plus["drift_velocity_m_s"] < 0.0
    assert meta_minus["drift_velocity_m_s"] > 0.0


def test_e3_builds_normalized_drift_only_joule_source() -> None:
    base = BASE.read_text(encoding="utf-8")
    text, meta = build_e3_joule_input(
        base,
        field_v_m=E3_FIELD_V_M,
        mobility_m2_v_s=E3_MOBILITY_M2_V_S,
    )
    assert mb.has_block(text, f"FVKernels/{E3_JOULE_KERNEL}")
    assert mp.get_parameter(text, f"FVKernels/{E3_JOULE_KERNEL}", "type") == "FVCoupledForce"
    assert mp.get_parameter(text, f"FVKernels/{E3_JOULE_KERNEL}", "variable") == ENERGY_VARIABLE
    assert mp.get_parameter(text, f"FVKernels/{E3_JOULE_KERNEL}", "v") == "n_e"
    assert float(mp.get_parameter(text, f"FVKernels/{E3_JOULE_KERNEL}", "coef") or "0") > 0.0
    assert meta["production_solved_field_joule_coupling_validated"] is False


def test_e4_thermal_energy_wall_is_six_solid_walls_only() -> None:
    base = BASE.read_text(encoding="utf-8")
    text, meta = build_e4_e5_wall_input(
        base,
        see_particle_on=False,
        see_energy_on=False,
    )
    assert mb.has_block(text, f"FVBCs/{ENERGY_WALL_THERMAL_BC}")
    boundary = mp.get_parameter(text, f"FVBCs/{ENERGY_WALL_THERMAL_BC}", "boundary") or ""
    assert "plasma_wafer" in boundary
    assert "plasma_focus_ring" in boundary
    assert "inlet" not in boundary
    assert "outlet" not in boundary
    assert float(mp.get_parameter(text, f"FVBCs/{ENERGY_WALL_THERMAL_BC}", "factor") or "nan") == -1.0
    assert mb.has_block(text, f"Postprocessors/{ENERGY_WALL_THERMAL_POWER_PP}")
    assert meta["thermal_energy_wall_enabled"] is True


def test_e5_see_energy_uses_a8_particle_flux_and_4ev_scale() -> None:
    base = BASE.read_text(encoding="utf-8")
    off, meta_off = build_e4_e5_wall_input(
        base,
        see_particle_on=True,
        see_energy_on=False,
    )
    on, meta_on = build_e4_e5_wall_input(
        base,
        see_particle_on=True,
        see_energy_on=True,
    )
    assert float(mp.get_parameter(off, f"FVBCs/{SEE_ENERGY_BC}", "factor") or "nan") == 0.0
    assert float(mp.get_parameter(on, f"FVBCs/{SEE_ENERGY_BC}", "factor") or "nan") == 1.0
    assert mb.has_block(on, f"Postprocessors/{SEE_ENERGY_COUPLED_POWER_PP}")
    assert meta_off["secondary_electron_mean_energy_eV"] == 4.0
    assert meta_on["secondary_electron_mean_energy_eV"] == 4.0
    assert meta_on["see_particle_enabled"] is True
    assert meta_on["see_energy_enabled"] is True
    assert meta_on["particle_transport_lookup_coupled_to_solved_energy"] is False
