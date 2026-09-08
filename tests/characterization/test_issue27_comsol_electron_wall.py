from __future__ import annotations

import math
from pathlib import Path

from experiments.Issue27_surface_reactions.controlled_wall.combined import (
    CHARGED,
    ELECTRON_BC as A6_ELECTRON_BC,
    PLASMA_WALLS,
    _charged_names,
)
from experiments.Issue27_surface_reactions.controlled_wall.electron_wall import (
    THERMAL_BC,
    THERMAL_FUNCTOR,
    THERMAL_MATERIAL,
    _build_a7_case_input,
    _thermal_speed_from_mean_energy,
    _validated_parameters,
)
from qpx_harness.application.experiment_spec import load_experiment_spec
from qpx_harness.adapters.moose import blocks as mb
from qpx_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue91_r3 import MEAN_ELECTRON_ENERGY_EV

ROOT = Path(__file__).resolve().parents[2]
R4_SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
A7_SPEC = ROOT / "experiments/Issue27_surface_reactions/A7_comsol_electron_wall/experiment.json"


def _factor(text: str, path: str) -> float:
    return float(mp.get_parameter(text, path, "factor") or "nan")


def test_issue27_a7_spec_freezes_comsol_icp_electron_wall_contract() -> None:
    spec = load_experiment_spec(A7_SPEC)
    frozen = _validated_parameters(spec.parameters)

    assert spec.protocol == "issue27-surface-reaction-controlled-wall"
    assert frozen["wall_model"] == "comsol_electron_thermal_wall_control"
    assert tuple(frozen["wall_boundaries"]) == PLASMA_WALLS
    assert frozen["electron_reflection_coefficient"] == 0.0
    assert frozen["electron_wall_migration"] is False
    assert frozen["secondary_emission_coefficient"] == 0.0
    assert frozen["electron_energy_wall_coupling"] is False
    assert math.isclose(
        float(frozen["electron_mean_energy_eV"]),
        MEAN_ELECTRON_ENERGY_EV,
        rel_tol=0.0,
        abs_tol=0.0,
    )


def test_issue27_a7_replaces_matched_ledger_with_thermal_particle_flux() -> None:
    spec = load_experiment_spec(A7_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_a7_case_input(
        base,
        parameters=spec.parameters,
        mode="electron_thermal_only",
    )

    assert meta["matched_a6_electron_ledger_removed"] is True
    assert not mb.has_block(text, f"FVBCs/{A6_ELECTRON_BC}")
    assert mb.has_block(text, f"FunctorMaterials/{THERMAL_MATERIAL}")
    assert mb.has_block(text, f"FVBCs/{THERMAL_BC}")
    assert mp.get_parameter(text, f"FVBCs/{THERMAL_BC}", "variable") == "n_e"
    assert tuple(
        mp.words(mp.get_parameter(text, f"FVBCs/{THERMAL_BC}", "boundary"))
    ) == PLASMA_WALLS
    assert mp.get_parameter(text, f"FVBCs/{THERMAL_BC}", "functor") == THERMAL_FUNCTOR
    assert _factor(text, f"FVBCs/{THERMAL_BC}") == -1.0

    expression = mp.get_parameter(
        text,
        f"FunctorMaterials/{THERMAL_MATERIAL}",
        "expression",
    )
    assert expression is not None
    assert "ne_hat" in expression
    assert "mean_ev" in expression
    assert "potential_plasma" not in expression
    assert mp.words(
        mp.get_parameter(text, f"FunctorMaterials/{THERMAL_MATERIAL}", "functor_names")
    ) == ["n_e", "mean_en"]


def test_issue27_a7_control_disables_thermal_wall_loss() -> None:
    spec = load_experiment_spec(A7_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, _ = _build_a7_case_input(
        base,
        parameters=spec.parameters,
        mode="control",
    )
    assert _factor(text, f"FVBCs/{THERMAL_BC}") == 0.0


def test_issue27_a7_combined_case_preserves_a6_ion_wall_migration() -> None:
    spec = load_experiment_spec(A7_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_a7_case_input(
        base,
        parameters=spec.parameters,
        mode="combined_thermal",
    )

    assert meta["a5_preflight"]["status"] == "PASS"
    assert _factor(text, f"FVBCs/{THERMAL_BC}") == -1.0
    for species in CHARGED:
        for wall in PLASMA_WALLS:
            surface_bc, migration_bc, _, _ = _charged_names(species, wall)
            assert _factor(text, f"FVBCs/{surface_bc}") == -1.0
            assert _factor(text, f"FVBCs/{migration_bc}") == -1.0


def test_issue27_a7_does_not_fake_an_electron_energy_equation() -> None:
    spec = load_experiment_spec(A7_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_a7_case_input(
        base,
        parameters=spec.parameters,
        mode="combined_thermal",
    )

    assert meta["electron_energy_wall_coupling"] is False
    assert "no electron-energy solver variable" in meta["electron_energy_deferral"]
    for candidate in ("electron_energy", "n_epsilon", "mean_energy"):
        assert not mb.has_block(text, f"Variables/{candidate}")


def test_issue27_a7_thermal_speed_matches_frozen_mean_energy() -> None:
    speed = _thermal_speed_from_mean_energy(MEAN_ELECTRON_ENERGY_EV)
    assert math.isclose(speed, 1.3083291166861567e6, rel_tol=1.0e-14)
