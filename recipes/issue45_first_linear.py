"""Issue45 first-linear construction as a thin composition over generic primitives."""
from __future__ import annotations

from typing import Any

from qpx_harness.moose import parameters as mp
from qpx_harness.petsc import options as po

TARGET = 1.0e16
DIAGNOSTIC_NL_MAX_ITS = 1
FIRST_LINEAR_PETSC_OPTIONS = (
    "-snes_test_jacobian",
    "-ksp_view",
    "-ksp_monitor_true_residual",
)
REQUIRED_EXISTING_OPTIONS = ("-snes_converged_reason", "-ksp_converged_reason")


def instrument_first_linear(text: str) -> tuple[str, dict[str, Any]]:
    out = mp.upsert_parameter(
        text,
        "Executioner",
        "nl_max_its",
        str(DIAGNOSTIC_NL_MAX_ITS),
    )
    out = po.add_flags(out, REQUIRED_EXISTING_OPTIONS + FIRST_LINEAR_PETSC_OPTIONS)
    return out, {
        "target": TARGET,
        "diagnostic_nl_max_its": DIAGNOSTIC_NL_MAX_ITS,
        "petsc_options_added": list(FIRST_LINEAR_PETSC_OPTIONS),
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "diagnostic_horizon_changed": True,
    }
