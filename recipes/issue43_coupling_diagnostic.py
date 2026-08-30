"""Issue43 diagnostic input construction over reusable MOOSE/PETSc primitives."""
from __future__ import annotations

from typing import Any

from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp
from qpx_harness.moose_input import MooseInput
from qpx_harness.petsc import options as po

DIAGNOSTIC_PETSC_OPTIONS = (
    "-snes_converged_reason",
    "-ksp_converged_reason",
    "-snes_monitor",
    "-ksp_monitor",
)
JACOBIAN_PETSC_OPTIONS = ("-snes_test_jacobian",)


def _ensure_debug_block(text: str) -> str:
    matches = MooseInput(text).find("Debug")
    if len(matches) > 1:
        raise mb.MooseBlockError("multiple top-level [Debug] blocks")
    if not matches:
        return mb.append_top_level_block(
            text,
            "[Debug]\n  show_var_residual_norms = true\n[]",
        )
    return mp.upsert_parameter(text, "Debug", "show_var_residual_norms", "true")


def instrument_input(
    input_text: str,
    *,
    jacobian_test: bool = False,
) -> tuple[str, dict[str, Any]]:
    text = _ensure_debug_block(input_text)
    text = mp.upsert_parameter(text, "Executioner", "verbose", "true")
    required = DIAGNOSTIC_PETSC_OPTIONS + (
        JACOBIAN_PETSC_OPTIONS if jacobian_test else ()
    )
    text = po.add_flags(text, required)
    text = mp.upsert_parameter(text, "Outputs/console", "all_variable_norms", "true")
    return text, {
        "debug_show_var_residual_norms": True,
        "executioner_verbose": True,
        "console_all_variable_norms": True,
        "petsc_options_added": list(required),
        "jacobian_test": jacobian_test,
        "physics_or_numerics_changed": False,
    }
