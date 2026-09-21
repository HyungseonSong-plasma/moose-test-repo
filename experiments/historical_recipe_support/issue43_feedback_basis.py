"""Accepted Issue43 closed electron/bulk-Poisson feedback basis.

This recipe owns the scientific composition of the accepted feedback model.
Reusable fixed-step and output-observation mechanics remain physics_harness
capabilities; versioned/Issue-numbered runtime facades are not dependencies.
"""
from __future__ import annotations

from typing import Any

from experiments.historical_recipe_support import issue43_fast_relaxation as fast_relaxation
from physics_harness.adapters.moose.executioner import apply_fixed_step_contract
from physics_harness.adapters.moose.output_observation import apply_microtime_output_contract

DT_REFERENCE = 1.0e-13
STEPS = 1

# Frozen accepted Issue43 anchors; generic scale analysis intentionally owns no defaults.
ACCEPTED_GAS_TEMPERATURE = 300.0
ACCEPTED_ELECTRON_DENSITY = 1.0e16


def build_closed_feedback_input(
    base_text: str,
    *,
    radial_span: float,
    dt: float = DT_REFERENCE,
    steps: int = STEPS,
) -> tuple[str, dict[str, Any]]:
    text, metadata = fast_relaxation.build_fast_input(
        base_text,
        gas_temperature=ACCEPTED_GAS_TEMPERATURE,
        electron_density=ACCEPTED_ELECTRON_DENSITY,
        dt=dt,
        end_time=dt * steps,
        radial_span=radial_span,
    )
    text = apply_fixed_step_contract(text, dt=dt, steps=steps)
    text = apply_microtime_output_contract(text, dt=dt)
    return text, {
        "issue43_feedback": metadata,
        "fixed_step": {"dt": dt, "steps": steps},
        "output_observation_contract": "microtime",
        "scientific_dependency": "accepted Issue43 closed electron/bulk-Poisson feedback basis",
        "versioned_qpx_facade_dependency": False,
    }
