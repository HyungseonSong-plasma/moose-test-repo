from __future__ import annotations

import math
from pathlib import Path

from experiments.Issue27_surface_reactions.controlled_wall.combined import PLASMA_WALLS
from experiments.Issue27_surface_reactions.controlled_wall.electron_wall import THERMAL_BC
from experiments.Issue27_surface_reactions.controlled_wall.electron_wall_stable import (
    A7_DISCRIMINATOR_DT_S,
)
from experiments.Issue27_surface_reactions.controlled_wall.see import (
    ELEMENTARY_CHARGE_C,
    SEE_BC,
    SEE_ENERGY_PP,
    SEE_FUNCTOR,
    SEE_MATERIAL,
    SEE_PP,
    _build_a8_case_input,
    _validated_parameters,
)
from physics_harness.application.experiment_spec import load_experiment_spec
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
R4_SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
A8_SPEC = ROOT / "experiments/Issue27_surface_reactions/A8_finite_see/experiment.json"


def _factor(text: str, path: str) -> float:
    return float(mp.get_parameter(text, path, "factor") or "nan")


def test_issue27_a8_spec_freezes_comsol_oxygen_see_contract() -> None:
    spec = load_experiment_spec(A8_SPEC)
    frozen = _validated_parameters(spec.parameters)

    assert spec.protocol == "issue27-surface-reaction-controlled-wall"
    assert frozen["wall_model"] == "finite_see_control"
    assert tuple(frozen["wall_boundaries"]) == PLASMA_WALLS
    assert frozen["excluded_boundaries"] == ["inlet", "outlet"]
    assert frozen["O2p_secondary_emission_coefficient"] == 0.05
    assert frozen["Op_secondary_emission_coefficient"] == 0.05
    assert frozen["secondary_electron_mean_energy_eV"] == 4.0
    assert frozen["electron_wall_migration"] is False
    assert frozen["electron_energy_equation_coupled"] is False


def test_issue27_a8_see_on_uses_positive_ion_surface_plus_migration_flux() -> None:
    spec = load_experiment_spec(A8_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_a8_case_input(base, parameters=spec.parameters, mode="see_on")

    assert mb.has_block(text, f"FunctorMaterials/{SEE_MATERIAL}")
    assert mb.has_block(text, f"FVBCs/{SEE_BC}")
    assert mb.has_block(text, f"Postprocessors/{SEE_PP}")
    assert mb.has_block(text, f"Postprocessors/{SEE_ENERGY_PP}")
    assert _factor(text, f"FVBCs/{THERMAL_BC}") == -1.0
    assert _factor(text, f"FVBCs/{SEE_BC}") == 1.0
    assert mp.get_parameter(text, f"FVBCs/{SEE_BC}", "variable") == "n_e"
    assert mp.get_parameter(text, f"FVBCs/{SEE_BC}", "functor") == SEE_FUNCTOR
    assert tuple(mp.words(mp.get_parameter(text, f"FVBCs/{SEE_BC}", "boundary"))) == PLASMA_WALLS

    functors = mp.words(
        mp.get_parameter(text, f"FunctorMaterials/{SEE_MATERIAL}", "functor_names")
    )
    assert functors == [
        "ion_surface_mass_flux_O2p",
        "ion_migration_mass_flux_O2p",
        "ion_surface_mass_flux_Op",
        "ion_migration_mass_flux_Op",
    ]
    expression = mp.get_parameter(text, f"FunctorMaterials/{SEE_MATERIAL}", "expression")
    assert expression is not None
    assert "o2ps" in expression and "o2pm" in expression
    assert "ops" in expression and "opm" in expression
    assert "Om" not in expression and "om" not in expression
    assert meta["see_enabled"] is True
    assert meta["electron_energy_equation_coupled"] is False
    assert meta["a8_discriminator_timestep_s"] == A7_DISCRIMINATOR_DT_S


def test_issue27_a8_see_off_is_exact_particle_and_energy_control() -> None:
    spec = load_experiment_spec(A8_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_a8_case_input(base, parameters=spec.parameters, mode="see_off")

    assert _factor(text, f"FVBCs/{SEE_BC}") == 0.0
    assert _factor(text, f"FVBCs/{THERMAL_BC}") == -1.0
    assert meta["see_enabled"] is False
    assert float(mp.get_parameter(text, "Executioner", "dt") or "nan") == 1.0e-10
    assert float(mp.get_parameter(text, "Executioner", "end_time") or "nan") == 1.0e-10


def test_issue27_a8_energy_ledger_is_four_ev_per_emitted_electron() -> None:
    spec = load_experiment_spec(A8_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_a8_case_input(base, parameters=spec.parameters, mode="see_on")

    n_ref = float(meta["electron_reference_density_m3"])
    expected_scale = n_ref * ELEMENTARY_CHARGE_C * 4.0
    assert mp.get_parameter(text, f"Postprocessors/{SEE_ENERGY_PP}", "type") == "ScalePostprocessor"
    assert mp.get_parameter(text, f"Postprocessors/{SEE_ENERGY_PP}", "value") == SEE_PP
    measured_scale = float(
        mp.get_parameter(text, f"Postprocessors/{SEE_ENERGY_PP}", "scaling_factor") or "nan"
    )
    assert math.isclose(measured_scale, expected_scale, rel_tol=1.0e-14, abs_tol=0.0)
    assert meta["secondary_electron_mean_energy_eV"] == 4.0
    assert "#26" in meta["electron_energy_handoff"]


def test_issue27_a8_does_not_fabricate_an_electron_energy_unknown() -> None:
    spec = load_experiment_spec(A8_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_a8_case_input(base, parameters=spec.parameters, mode="see_on")

    assert meta["electron_energy_equation_coupled"] is False
    for candidate in ("electron_energy", "n_epsilon", "mean_energy", "electron_mean_energy"):
        assert not mb.has_block(text, f"Variables/{candidate}")
