"""Issue45 closed/source-free electron-inventory nullspace policy.

This policy establishes the structural premise used by the inventory-constraint
experiment: with the accepted closed electron flux boundary treatment and no
source term, the steady spatial electron residual has the aggregate left-null
identity represented by ``[1^T, 0]`` for the electron/Poisson block.
"""
from __future__ import annotations

from typing import Any

from experiments.historical_recipe_support import issue45_inventory_constraint as constraint_policy
from physics_harness.adapters.moose.preflight import validate_parser_symbols_text

ISSUE = 45
EXPECTED_TRANSIENT_ELECTRON_KERNEL_TYPES = (
    "FVDiffusion",
    "FVTimeKernel",
    constraint_policy.DRIFT_TYPE,
)


def audit_closed_electron_structure(text: str) -> dict[str, Any]:
    """Audit prerequisites for the accepted closed/source-free nullspace identity."""
    checks: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, observed: Any, required: Any) -> None:
        checks.append(
            {
                "id": check_id,
                "status": "PASS" if passed else "FAIL",
                "observed": observed,
                "required": required,
            }
        )

    parser_errors = validate_parser_symbols_text(text, "<issue45-inventory-audit>")
    add("parser-symbol-preflight", not parser_errors, parser_errors, [])

    electron_kernels = constraint_policy._electron_kernel_records(text)
    observed_types = sorted(item["type"] for item in electron_kernels if item["type"])
    expected_types = sorted(EXPECTED_TRANSIENT_ELECTRON_KERNEL_TYPES)
    add(
        "electron-kernel-set",
        observed_types == expected_types and len(electron_kernels) == 3,
        electron_kernels,
        expected_types,
    )
    constraint_policy._flux_boundary_audit(text, electron_kernels, add)
    electron_bcs = constraint_policy._electron_fvbcs(text)
    add("no-electron-fvbc", not electron_bcs, electron_bcs, [])
    constraint_policy._audit_poisson_grounding(text, add)

    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": (
            "CLOSED_SOURCE_FREE_ELECTRON_STRUCTURE_PASS"
            if not blockers
            else "CONSERVATION_STRUCTURE_FAIL"
        ),
        "checks": checks,
        "blockers": blockers,
        "electron_kernels": electron_kernels,
        "electron_fvbcs": electron_bcs,
        "left_null_vector": "[1^T, 0]" if not blockers else None,
        "derivation_scope": (
            "steady spatial n_e residual only; transient FVTimeKernel excluded "
            "from the nullspace identity"
        ),
    }
