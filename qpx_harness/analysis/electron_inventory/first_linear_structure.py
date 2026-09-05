"""Canonical first-linear structure normalization and audit."""
from __future__ import annotations

from typing import Any

from recipes import issue45_first_linear as first_linear_recipe
from recipes import issue45_inventory_constraint as inventory_policy

from qpx_harness.moose import parameters as mp
from qpx_harness.petsc import options as petsc_options

TARGET = first_linear_recipe.TARGET
FIRST_LINEAR_PETSC_OPTIONS = first_linear_recipe.FIRST_LINEAR_PETSC_OPTIONS
REQUIRED_EXISTING_OPTIONS = first_linear_recipe.REQUIRED_EXISTING_OPTIONS


def _normalized_diagnostic_text(text: str) -> str:
    out = mp.upsert_parameter(
        text,
        "Executioner",
        "nl_max_its",
        "<DIAGNOSTIC_NL_MAX_ITS>",
    )
    return mp.upsert_parameter(
        out,
        "Executioner",
        "petsc_options",
        "'<DIAGNOSTIC_PETSC_OPTIONS>'",
    )


def audit_first_linear_structure(
    base_text: str, diagnostic_text: str
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, observed: Any, required: Any) -> None:
        checks.append(
            {
                "id": name,
                "status": "PASS" if ok else "FAIL",
                "observed": observed,
                "required": required,
            }
        )

    closure = inventory_policy.audit_constrained_quasisteady_structure(
        diagnostic_text,
        expected_macro_avg=TARGET,
    )
    add(
        "canonical-c0-closure-structure",
        closure["status"] == "PASS",
        closure["status"],
        "PASS",
    )
    nl_max = mp.unquote(mp.get_parameter(diagnostic_text, "Executioner", "nl_max_its"))
    add("first-linear-nonlinear-horizon", nl_max == "1", nl_max, "1")

    options = petsc_options.get_flags(diagnostic_text)
    add(
        "existing-reason-options-preserved",
        all(option in options for option in REQUIRED_EXISTING_OPTIONS),
        options,
        list(REQUIRED_EXISTING_OPTIONS),
    )
    for option in FIRST_LINEAR_PETSC_OPTIONS:
        add(f"diagnostic-option:{option}", option in options, options, option)
    add(
        "no-full-jacobian-matrix-dump",
        "-snes_test_jacobian_view" not in options,
        options,
        "absent",
    )

    pairs = petsc_options.get_name_value_pairs(diagnostic_text)
    inames = [name for name, _ in pairs]
    values = [value for _, value in pairs]
    add(
        "lu-nonzero-shift-preserved",
        inames == ["-pc_type", "-pc_factor_shift_type"]
        and values == ["lu", "NONZERO"],
        {"iname": inames, "value": values},
        {
            "iname": ["-pc_type", "-pc_factor_shift_type"],
            "value": ["lu", "NONZERO"],
        },
    )

    same = _normalized_diagnostic_text(base_text) == _normalized_diagnostic_text(
        diagnostic_text
    )
    add("diagnostic-only-input-difference", same, same, True)
    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": (
            "FIRST_LINEAR_STRUCTURE_PASS"
            if not blockers
            else "FIRST_LINEAR_STRUCTURE_FAIL"
        ),
        "checks": checks,
        "blockers": blockers,
        "closure": closure,
    }
