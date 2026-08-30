"""Issue43 diagnostic input construction over reusable MOOSE/PETSc primitives."""
from __future__ import annotations

from typing import Any

from qpx_harness.moose import parameters as mp
from qpx_harness.petsc import options as po
from qpx_harness import fast_plasma_coupling_diagnostic as legacy


def instrument_input(
    input_text: str,
    *,
    jacobian_test: bool = False,
) -> tuple[str, dict[str, Any]]:
    # Debug block creation is a later generic block/output seam. Reuse the accepted
    # constructor for that single operation while parameter/PETSc mutation is shared.
    text = legacy._ensure_debug_block(input_text)
    text = mp.upsert_parameter(text, "Executioner", "verbose", "true")
    required = legacy.DIAGNOSTIC_PETSC_OPTIONS + (
        legacy.JACOBIAN_PETSC_OPTIONS if jacobian_test else ()
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
