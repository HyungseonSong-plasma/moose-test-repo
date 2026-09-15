from __future__ import annotations

from pathlib import Path

from experiments.historical_recipe_support.issue192_s5r import (
    audit_s5r_input,
    build_s5r_input,
)
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
ENERGY_DRIFT = "FVKernels/s5r_n_epsilon_drift"
PARTICLE_DRIFT = "FVKernels/n_e_drift"
TOPOLOGY = (
    "potential",
    "carrier",
    "charge_number",
    "advected_interp_method",
    "boundaries_to_avoid",
    "block",
)


def _build() -> str:
    text, _meta = build_s5r_input(BASE.read_text())
    return text


def test_s5r_energy_transport_has_time_diffusion_and_drift() -> None:
    text = _build()
    assert mb.has_block(text, "FVKernels/s5r_n_epsilon_time")
    assert mb.has_block(text, "FVKernels/s5r_n_epsilon_diffusion")
    assert mb.has_block(text, ENERGY_DRIFT)
    assert mp.get_parameter(text, ENERGY_DRIFT, "type") == "PhysicsFVElectrostaticDrift"
    assert mp.get_parameter(text, ENERGY_DRIFT, "variable") == "n_epsilon"
    assert mp.get_parameter(text, ENERGY_DRIFT, "mobility") == "electron_energy_mobility"
    assert audit_s5r_input(text)["checks"]["solved_energy_transport_complete"] is True


def test_s5r_energy_drift_matches_particle_topology() -> None:
    text = _build()
    for parameter in TOPOLOGY:
        assert mp.get_parameter(text, ENERGY_DRIFT, parameter) == mp.get_parameter(
            text, PARTICLE_DRIFT, parameter
        )


def test_s5r_energy_drift_mutation_fails_audit() -> None:
    text = _build()
    mutated = mp.upsert_parameter(text, ENERGY_DRIFT, "charge_number", "1")
    mutated_audit = audit_s5r_input(mutated)
    assert mutated_audit["status"] == "FAIL"
    assert mutated_audit["checks"]["solved_energy_transport_complete"] is False
