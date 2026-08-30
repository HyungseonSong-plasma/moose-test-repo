"""Issue46 Jacobian-localization construction over generic MOOSE/PETSc primitives."""
from __future__ import annotations

from typing import Any

from qpx_harness.moose import blocks as mb
from qpx_harness.petsc import options as po

TARGET = 1.0e16
LOCALIZATION_THRESHOLD = 1.0e-7
DOFMAP_OUTPUT = "r46_dofmap"
DOFMAP_FILE_BASE = "r46_dofmap"


def _add_dofmap_output(text: str) -> str:
    path = f"Outputs/{DOFMAP_OUTPUT}"
    mb.require_absent(text, path)
    block = (
        f"  [{DOFMAP_OUTPUT}]\n"
        "    type = DOFMap\n"
        "    execute_on = INITIAL\n"
        f"    file_base = {DOFMAP_FILE_BASE}\n"
        "  []"
    )
    return mb.insert_child_block(text, "Outputs", block)


def instrument_localization(first_linear_text: str) -> tuple[str, dict[str, Any]]:
    out = po.remove_flags(first_linear_text, ["-snes_test_jacobian"])
    out = po.add_flags(out, ["-snes_test_jacobian_view"])
    out = po.upsert_name_value(
        out,
        "-snes_test_jacobian",
        f"{LOCALIZATION_THRESHOLD:.12g}",
    )
    out = _add_dofmap_output(out)
    return out, {
        "target": TARGET,
        "localization_threshold": LOCALIZATION_THRESHOLD,
        "dofmap_output": DOFMAP_OUTPUT,
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "scaling_policy_changed": False,
        "diagnostic_observability_only": True,
    }
