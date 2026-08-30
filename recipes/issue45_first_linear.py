"""Issue45 first-linear construction as a thin composition over generic primitives."""
from __future__ import annotations

from typing import Any

from qpx_harness.moose import parameters as mp
from qpx_harness.petsc import options as po
from qpx_harness import petsc_first_linear_diagnostic as legacy


def instrument_first_linear(text: str) -> tuple[str, dict[str, Any]]:
    out = mp.upsert_parameter(
        text,
        "Executioner",
        "nl_max_its",
        str(legacy.DIAGNOSTIC_NL_MAX_ITS),
    )
    required = legacy.REQUIRED_EXISTING_OPTIONS + legacy.FIRST_LINEAR_PETSC_OPTIONS
    out = po.add_flags(out, required)
    return out, {
        "target": legacy.TARGET,
        "diagnostic_nl_max_its": legacy.DIAGNOSTIC_NL_MAX_ITS,
        "petsc_options_added": list(legacy.FIRST_LINEAR_PETSC_OPTIONS),
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "diagnostic_horizon_changed": True,
    }
