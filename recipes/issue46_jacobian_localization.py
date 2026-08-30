"""Issue46 Jacobian-localization construction over generic PETSc primitives."""
from __future__ import annotations

from typing import Any

from qpx_harness.petsc import options as po
from qpx_harness import augmented_jacobian_localization as legacy


def instrument_localization(first_linear_text: str) -> tuple[str, dict[str, Any]]:
    out = po.remove_flags(first_linear_text, ["-snes_test_jacobian"])
    out = po.add_flags(out, ["-snes_test_jacobian_view"])
    out = po.upsert_name_value(
        out,
        "-snes_test_jacobian",
        f"{legacy.LOCALIZATION_THRESHOLD:.12g}",
    )
    # DOFMap block extraction is a later MOOSE-output primitive seam. Until then,
    # retain the accepted Issue46 block constructor while PETSc mutation is shared.
    out = legacy._add_dofmap_output(out)
    return out, {
        "target": legacy.TARGET,
        "localization_threshold": legacy.LOCALIZATION_THRESHOLD,
        "dofmap_output": legacy.DOFMAP_OUTPUT,
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "scaling_policy_changed": False,
        "diagnostic_observability_only": True,
    }
