#!/usr/bin/env python3
"""P0 characterization for Issue45 inventory-constraint recipe migration."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.adapters.moose.electron_inventory import closure_model
from qpx_harness.analysis.electron_inventory import closure_runtime, structure
from qpx_harness.execution.electron_inventory import orchestration
from qpx_harness.adapters.moose.electron_inventory.constants import (
    C0_TARGET,
    C1_TARGET,
    DEFAULT_MACRO_ELECTRON_AVG,
    LAMBDA_VARIABLE,
)
from experiments.historical_recipe_support import issue45_closure_basis as closure_basis
from experiments.historical_recipe_support import issue45_inventory_constraint as recipe


def _assert_equal(label: str, new: object, old: object) -> None:
    if new != old:
        raise AssertionError(f"{label} drift:\nnew={new!r}\nold={old!r}")


def _accepted_feedback() -> tuple[str, str, float]:
    _, base_text, radial_span = orchestration._base_case_context()
    feedback, _ = closure_basis.build_closed_feedback_input(
        base_text,
        dt=1.0e-13,
        steps=1,
        radial_span=radial_span,
    )
    return base_text, feedback, radial_span


def _check_construction() -> None:
    base_text, feedback, radial_span = _accepted_feedback()
    for target in (C0_TARGET, C1_TARGET):
        canonical_text = closure_model._build_constrained_quasisteady_input(
            base_text,
            radial_span=radial_span,
            macro_avg=target,
            runtime_observability=True,
        )
        recipe_text = recipe.build_constrained_quasisteady_input(
            feedback,
            macro_avg=target,
            runtime_observability=True,
        )
        _assert_equal(f"constrained-input:{target:.17g}", recipe_text, canonical_text)


def _check_structure_policy() -> None:
    constrained = closure_model._synthetic_constrained_input()
    cases = {
        "positive": (constrained, "PASS"),
        "retained-time-kernel": (
            constrained.replace(
                "[FVKernels]\n",
                "[FVKernels]\n  [time]\n    type = FVTimeKernel\n    variable = n_e\n  []\n",
                1,
            ),
            "HOLD",
        ),
        "wrong-target": (
            constrained.replace(
                f"value = {DEFAULT_MACRO_ELECTRON_AVG:.17g}",
                "value = 2e16",
                1,
            ),
            "HOLD",
        ),
        "wrong-lambda": (
            constrained.replace(
                f"lambda = {LAMBDA_VARIABLE}",
                "lambda = missing_lambda",
                1,
            ),
            "HOLD",
        ),
    }
    for name, (text, expected_status) in cases.items():
        recipe_result = recipe.audit_constrained_quasisteady_structure(
            text, expected_macro_avg=DEFAULT_MACRO_ELECTRON_AVG
        )
        canonical_result = structure.audit_constrained_quasisteady_structure(
            text, expected_macro_avg=DEFAULT_MACRO_ELECTRON_AVG
        )
        if recipe_result["status"] != expected_status or canonical_result["status"] != expected_status:
            raise AssertionError(
                f"structure:{name} status drift: recipe={recipe_result['status']} canonical={canonical_result['status']}"
            )
        _assert_equal(
            f"structure:{name}:checks",
            recipe_result.get("checks"),
            canonical_result.get("checks"),
        )


def _check_pair_policy() -> None:
    c0 = closure_model._synthetic_constrained_input(C0_TARGET)
    c1 = closure_model._synthetic_constrained_input(C1_TARGET)
    for name, right in (
        ("positive", c1),
        ("non-target-mutation", c1.replace("boundary = outlet", "boundary = plasma_cover", 1)),
    ):
        _assert_equal(
            f"pair:{name}",
            recipe.target_only_pair_audit(c0, right),
            closure_model._target_only_pair_audit(c0, right),
        )


def _good_diag() -> dict[str, object]:
    return {
        "pc_failure_reason": None,
        "nonlinear_reason": None,
        "nonfinite_residuals": [],
        "variable_residuals": [
            {
                "n_e": 1.0e-10,
                "potential_plasma": 1.0e-12,
                LAMBDA_VARIABLE: 1.0e-11,
            }
        ],
    }


def _check_runtime_policy() -> None:
    good_diag = _good_diag()
    positive = {
        "target": C0_TARGET,
        "returncode": 0,
        "converged_marker": True,
        "diagnostic": good_diag,
        "row": closure_runtime._synthetic_runtime_row(C0_TARGET),
    }
    bad_row = closure_runtime._synthetic_runtime_row(C1_TARGET)
    bad_row["n_avg"] = C1_TARGET * 1.001
    bad_row["inventory"] = bad_row["n_avg"] * bad_row["domain_volume"]
    cases = {
        "positive": positive,
        "target-tracking": {
            "target": C1_TARGET,
            "returncode": 0,
            "converged_marker": True,
            "diagnostic": good_diag,
            "row": bad_row,
        },
        "zero-pivot": {
            "target": C0_TARGET,
            "returncode": 1,
            "converged_marker": False,
            "diagnostic": {
                **good_diag,
                "pc_failure_reason": "FACTOR_NUMERIC_ZEROPIVOT",
            },
            "row": None,
        },
        "missing-residuals": {
            "target": C0_TARGET,
            "returncode": 0,
            "converged_marker": True,
            "diagnostic": {**good_diag, "variable_residuals": []},
            "row": closure_runtime._synthetic_runtime_row(C0_TARGET),
        },
    }
    for name, kwargs in cases.items():
        recipe_result = recipe.evaluate_runtime_case_data(**kwargs)
        canonical_result = closure_runtime._evaluate_runtime_case_data(**kwargs)
        for key in recipe_result:
            if canonical_result.get(key) != recipe_result[key]:
                raise AssertionError(
                    f"runtime-case:{name}:{key} drift: {canonical_result.get(key)!r} != {recipe_result[key]!r}"
                )

    c0 = recipe.evaluate_runtime_case_data(
        target=C0_TARGET,
        returncode=0,
        converged_marker=True,
        diagnostic=good_diag,
        row=closure_runtime._synthetic_runtime_row(C0_TARGET),
    )
    c1 = recipe.evaluate_runtime_case_data(
        target=C1_TARGET,
        returncode=0,
        converged_marker=True,
        diagnostic=good_diag,
        row=closure_runtime._synthetic_runtime_row(C1_TARGET),
    )
    _assert_equal(
        "runtime-pair:positive",
        recipe.evaluate_runtime_pair(c0, c1, target0=C0_TARGET, target1=C1_TARGET),
        closure_runtime._evaluate_runtime_pair(c0, c1, target0=C0_TARGET, target1=C1_TARGET),
    )


def _check_primitive_boundary() -> None:
    source = (ROOT / "recipes" / "issue45_inventory_constraint.py").read_text()
    for required in (
        "from qpx_harness.adapters.moose import blocks as mb",
        "from qpx_harness.adapters.moose import parameters as mp",
    ):
        if required not in source:
            raise AssertionError(f"missing generic primitive import: {required}")
    for forbidden in (
        "electron_inventory_nullspace",
        "fast_plasma_relaxation",
        "petsc_first_linear_diagnostic",
        "augmented_jacobian_localization",
        "jacobian_fd_reference_audit",
    ):
        if forbidden in source:
            raise AssertionError(
                f"reverse dependency leaked into Issue45 inventory recipe: {forbidden}"
            )


def main() -> int:
    try:
        _check_construction()
        print("ISSUE48_WP4_ISSUE45_INVENTORY_CHECK: construction=PASS")
        _check_structure_policy()
        print("ISSUE48_WP4_ISSUE45_INVENTORY_CHECK: structure-policy=PASS")
        _check_pair_policy()
        print("ISSUE48_WP4_ISSUE45_INVENTORY_CHECK: target-pair-policy=PASS")
        _check_runtime_policy()
        print("ISSUE48_WP4_ISSUE45_INVENTORY_CHECK: runtime-policy=PASS")
        _check_primitive_boundary()
        print("ISSUE48_WP4_ISSUE45_INVENTORY_CHECK: recipe-reverse-dependency=NONE")
    except Exception as exc:
        print(f"ISSUE48_WP4_ISSUE45_INVENTORY_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP4_ISSUE45_INVENTORY_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
