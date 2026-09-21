"""Issue45 closure basis composed from accepted Issue43 feedback semantics.

Issue43 owns the accepted closed electron/bulk-Poisson feedback basis. Issue45
adds only its inventory constraint on top of that scientific dependency.
"""
from __future__ import annotations

from typing import Any

from experiments.historical_recipe_support import issue43_feedback_basis as feedback_basis
from experiments.historical_recipe_support import issue45_inventory_constraint as inventory_constraint

ISSUE = 45
DT_REFERENCE = feedback_basis.DT_REFERENCE
STEPS = feedback_basis.STEPS
ACCEPTED_GAS_TEMPERATURE = feedback_basis.ACCEPTED_GAS_TEMPERATURE
ACCEPTED_ELECTRON_DENSITY = feedback_basis.ACCEPTED_ELECTRON_DENSITY


def build_closed_feedback_input(
    base_text: str,
    *,
    radial_span: float,
    dt: float = DT_REFERENCE,
    steps: int = STEPS,
) -> tuple[str, dict[str, Any]]:
    return feedback_basis.build_closed_feedback_input(
        base_text,
        radial_span=radial_span,
        dt=dt,
        steps=steps,
    )


def build_constrained_quasisteady_input(
    base_text: str,
    *,
    radial_span: float,
    macro_avg: float,
    runtime_observability: bool = True,
) -> tuple[str, dict[str, Any]]:
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
