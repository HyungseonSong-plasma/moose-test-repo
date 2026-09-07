from __future__ import annotations

import math
from pathlib import Path

from experiments.Issue27_surface_reactions.controlled_wall.combined import (
    CHARGED,
    ELECTRON_BC,
    O_RETURN_BC,
    PLASMA_WALLS,
    _a5_preflight,
    _build_a6_case_input,
    _charged_names,
    _validated_parameters,
)
from qpx_harness.application.experiment_spec import load_experiment_spec
from qpx_harness.adapters.moose import blocks as mb
from qpx_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
R4_SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
A6_SPEC = ROOT / "experiments/Issue27_surface_reactions/A6_combined_wall_integration/experiment.json"
EXPECTED_WALLS = (
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)


def _factor(text: str, path: str) -> float:
    return float(mp.get_parameter(text, path, "factor") or "nan")


def test_issue27_a6_spec_freezes_comsol_phase_a_contract() -> None:
    spec = load_experiment_spec(A6_SPEC)
    frozen = _validated_parameters(spec.parameters)

    assert spec.protocol == "issue27-surface-reaction-controlled-wall"
    assert frozen["wall_model"] == "combined_comsol_wall_control"
    assert tuple(frozen["wall_boundaries"]) == EXPECTED_WALLS
    assert frozen["excluded_boundaries"] == ["inlet", "outlet"]
    assert frozen["secondary_emission"] is False
    assert frozen["production_electron_sheath"] is False
    assert math.isclose(float(frozen["O_sticking_coefficient"]), 0.2)
    assert math.isclose(float(frozen["O2s_sticking_coefficient"]), 1.0)
    assert math.isclose(float(frozen["Os_sticking_coefficient"]), 0.2)
    assert math.isclose(float(frozen["O2p_sticking_coefficient"]), 1.0)
    assert math.isclose(float(frozen["Om_sticking_coefficient"]), 1.0)
    assert math.isclose(float(frozen["Op_sticking_coefficient"]), 1.0)


def test_issue27_a5_preflight_and_comsol_wall_ownership() -> None:
    spec = load_experiment_spec(A6_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_a6_case_input(base, parameters=spec.parameters, mode="comsol_wall")
    preflight = _a5_preflight(text, meta)

    assert preflight["status"] == "PASS"
    assert preflight["independent_O2_variable"] is False
    assert preflight["constrained_O2"] is True
    assert preflight["charged_interior_wall_double_counting_avoided"] is True
    assert preflight["comsol_wall_object"] == "QPXIonWallFluxMaterial"
    assert not mb.has_block(text, "Variables/w_O2")

    for species, cfg in CHARGED.items():
        material = f"FunctorMaterials/issue27_a6_{species}_wall_flux"
        assert mp.get_parameter(text, material, "type") == "QPXIonWallFluxMaterial"
        assert mp.get_parameter(text, material, "potential") == "potential_plasma"
        assert mp.get_parameter(text, material, "mobility") == cfg["mobility"]
        assert int(mp.get_parameter(text, material, "charge_number") or "0") == int(cfg["charge"])
        assert mp.get_parameter(text, material, "declare_suffix") == species

    for kernel in ("O2p_electrostatic_drift", "Om_electrostatic_drift", "Op_electrostatic_drift"):
        avoided = tuple(mp.words(mp.get_parameter(text, f"FVKernels/{kernel}", "boundaries_to_avoid")))
        assert "inlet" in avoided
        assert "outlet" in avoided
        for wall in EXPECTED_WALLS:
            assert wall in avoided


def test_issue27_a6_surface_only_disables_migration_but_comsol_enables_it() -> None:
    spec = load_experiment_spec(A6_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    surface_text, _ = _build_a6_case_input(base, parameters=spec.parameters, mode="surface_only")
    comsol_text, _ = _build_a6_case_input(base, parameters=spec.parameters, mode="comsol_wall")

    for species in CHARGED:
        for wall in PLASMA_WALLS:
            surface_bc, migration_bc, _, _ = _charged_names(species, wall)
            assert _factor(surface_text, f"FVBCs/{surface_bc}") == -1.0
            assert _factor(surface_text, f"FVBCs/{migration_bc}") == 0.0
            assert _factor(comsol_text, f"FVBCs/{surface_bc}") == -1.0
            assert _factor(comsol_text, f"FVBCs/{migration_bc}") == -1.0
            assert mp.get_parameter(
                comsol_text, f"FVBCs/{surface_bc}", "functor"
            ) == f"ion_surface_mass_flux_{species}"
            assert mp.get_parameter(
                comsol_text, f"FVBCs/{migration_bc}", "functor"
            ) == f"ion_migration_mass_flux_{species}"


def test_issue27_a6_keeps_neutralization_and_electron_ledger_separate() -> None:
    spec = load_experiment_spec(A6_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_a6_case_input(base, parameters=spec.parameters, mode="comsol_wall")

    assert _factor(text, f"FVBCs/{O_RETURN_BC}") == 1.0
    assert _factor(text, f"FVBCs/{ELECTRON_BC}") == -1.0
    assert mp.get_parameter(text, f"FVBCs/{O_RETURN_BC}", "variable") == "w_O"
    assert mp.get_parameter(text, f"FVBCs/{ELECTRON_BC}", "variable") == "n_e"
    assert meta["frozen_phase"]["secondary_emission"] is False
    assert meta["frozen_phase"]["production_electron_sheath"] is False
    assert "QPXIonWallFluxMaterial" in meta["charged_wall_material"]
    assert "one-sided" in meta["charged_wall_contract"]
