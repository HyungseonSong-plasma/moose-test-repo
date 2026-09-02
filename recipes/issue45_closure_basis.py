"""Issue45 closure basis composed from accepted Issue43 feedback semantics.

This recipe boundary makes the scientific dependency explicit: Issue45 starts
from the accepted Issue43 closed electron/bulk-Poisson feedback construction,
then applies the Issue45 inventory constraint.  Versioned qpx_harness facades
are intentionally not part of this dependency.
"""
from __future__ import annotations

from typing import Any

from recipes import issue43_fast_relaxation as issue43_feedback
from recipes import issue45_inventory_constraint as inventory_constraint
from qpx_harness.moose.executioner import apply_fixed_step_contract
from qpx_harness.moose.output_observation import apply_microtime_output_contract
from qpx_harness.scale_audit import DEFAULT_ELECTRON_DENSITY, DEFAULT_GAS_TEMPERATURE

ISSUE = 45
DT_REFERENCE = 1.0e-13
STEPS = 1
ACCEPTED_GAS_TEMPERATURE = DEFAULT_GAS_TEMPERATURE
ACCEPTED_ELECTRON_DENSITY = DEFAULT_ELECTRON_DENSITY


def build_closed_feedback_input(
    base_text: str,
    *,
    radial_span: float,
    dt: float = DT_REFERENCE,
    steps: int = STEPS,
) -> tuple[str, dict[str, Any]]:
    """Build the accepted closed feedback basis without a versioned runtime facade."""
    text, metadata = issue43_feedback.build_fast_input(
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


def build_constrained_quasisteady_input(
    base_text: str,
    *,
    radial_span: float,
    macro_avg: float,
    runtime_observability: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Compose the accepted feedback basis with the Issue45 inventory closure."""
    feedback, feedback_meta = build_closed_feedback_input(
        base_text,
        radial_span=radial_span,
    )
    constrained = inventory_constraint.build_constrained_quasisteady_input(
        feedback,
        macro_avg=macro_avg,
        runtime_observability=runtime_observability,
    )
    return constrained, {
        "feedback_basis": feedback_meta,
        "macro_electron_average": macro_avg,
        "runtime_observability": runtime_observability,
        "closure_policy": "integral n_e dV = N_e,macro via scalar Lagrange multiplier",
    }
