#!/usr/bin/env python3
"""P0 characterization for Issue45 inventory-constraint recipe migration."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import electron_inventory_nullspace as legacy
from recipes import issue45_inventory_constraint as recipe


def _assert_equal(label: str, new: object, old: object) -> None:
    if new != old:
        raise AssertionError(f"{label} drift:\nnew={new!r}\nold={old!r}")


def _accepted_feedback() -> tuple[str, str, float]:
    _, base_text, radial_span = legacy._base_case_context()
    feedback = legacy.v5._build_feedback_v5(
        base_text,
        dt=legacy.DT_REFERENCE,
        steps=legacy.STEPS,
        radial_span=radial_span,
    )
    return base_text, feedback, radial_span


def _check_construction() -> None:
    base_text, feedback, radial_span = _accepted_feedback()
    for target in (legacy.C0_TARGET, legacy.C1_TARGET):
        old_text = legacy._build_constrained_quasisteady_input(
            base_text,
            radial_span=radial_span,
            macro_avg=target,
            runtime_observability=True,
        )
        new_text = recipe.build_constrained_quasisteady_input(
            feedback,
            macro_avg=target,
            runtime_observability=True,
        )
        _assert_equal(f"constrained-input:{target:.17g}", new_text, old_text)


def _check_structure_policy() -> None:
    constrained = legacy._synthetic_constrained_input()
    cases = {
        "positive": constrained,
        "retained-time-kernel": constrained.replace(
            "[FVKernels]\n",
            "[FVKernels]\n  [time]\n    type = FVTimeKernel\n    variable = n_e\n  []\n",
            1,
        ),
        "wrong-target": constrained.replace(
            f"value = {legacy.DEFAULT_MACRO_ELECTRON_AVG:.17g}",
            "value = 2e16",
            1,
        ),
        "wrong-lambda": constrained.replace(
            f"lambda = {legacy.LAMBDA_VARIABLE}",
            "lambda = missing_lambda",
            1,
        ),
    }
    for name, text in cases.items():
        _assert_equal(
            f"structure:{name}",
            recipe.audit_constrained_quasisteady_structure(
                text, expected_macro_avg=legacy.DEFAULT_MACRO_ELECTRON_AVG
            ),
            legacy.audit_constrained_quasisteady_structure(
                text, expected_macro_avg=legacy.DEFAULT_MACRO_ELECTRON_AVG
            ),
        )


def _check_pair_policy() -> None:
    c0 = legacy._synthetic_constrained_input(legacy.C0_TARGET)
    c1 = legacy._synthetic_constrained_input(legacy.C1_TARGET)
    for name, right in (
        ("positive", c1),
        ("non-target-mutation", c1.replace("boundary = outlet", "boundary = plasma_cover", 1)),
    ):
        _assert_equal(
            f"pair:{name}",
            recipe.target_only_pair_audit(c0, right),
            legacy._target_only_pair_audit(c0, right),
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
                legacy.LAMBDA_VARIABLE: 1.0e-11,
            }
        ],
    }


def _check_runtime_policy() -> None:
    good_diag = _good_diag()
    positive = {
        "target": legacy.C0_TARGET,
        "returncode": 0,
        "converged_marker": True,
        "diagnostic": good_diag,
        "row": legacy._synthetic_runtime_row(legacy.C0_TARGET),
    }
    bad_row = legacy._synthetic_runtime_row(legacy.C1_TARGET)
    bad_row["n_avg"] = legacy.C1_TARGET * 1.001
    bad_row["inventory"] = bad_row["n_avg"] * bad_row["domain_volume"]
    cases = {
        "positive": positive,
        "target-tracking": {
            "target": legacy.C1_TARGET,
            "returncode": 0,
            "converged_marker": True,
            "diagnostic": good_diag,
            "row": bad_row,
        },
        "zero-pivot": {
            "target": legacy.C0_TARGET,
            "returncode": 1,
            "converged_marker": False,
            "diagnostic": {
                **good_diag,
                "pc_failure_reason": "FACTOR_NUMERIC_ZEROPIVOT",
            },
            "row": None,
        },
        "missing-residuals": {
            "target": legacy.C0_TARGET,
            "returncode": 0,
            "converged_marker": True,
            "diagnostic": {**good_diag, "variable_residuals": []},
            "row": legacy._synthetic_runtime_row(legacy.C0_TARGET),
        },
    }
    for name, kwargs in cases.items():
        _assert_equal(
            f"runtime-case:{name}",
            recipe.evaluate_runtime_case_data(**kwargs),
            legacy._evaluate_runtime_case_data(**kwargs),
        )

    c0 = recipe.evaluate_runtime_case_data(
        target=legacy.C0_TARGET,
        returncode=0,
        converged_marker=True,
        diagnostic=good_diag,
        row=legacy._synthetic_runtime_row(legacy.C0_TARGET),
    )
    c1 = recipe.evaluate_runtime_case_data(
        target=legacy.C1_TARGET,
        returncode=0,
        converged_marker=True,
        diagnostic=good_diag,
        row=legacy._synthetic_runtime_row(legacy.C1_TARGET),
    )
    _assert_equal(
        "runtime-pair:positive",
        recipe.evaluate_runtime_pair(
            c0, c1, target0=legacy.C0_TARGET, target1=legacy.C1_TARGET
        ),
        legacy._evaluate_runtime_pair(
            c0, c1, target0=legacy.C0_TARGET, target1=legacy.C1_TARGET
        ),
    )


def _check_primitive_boundary() -> None:
    source = (ROOT / "recipes" / "issue45_inventory_constraint.py").read_text()
    for required in (
        "from qpx_harness.moose import blocks as mb",
        "from qpx_harness.moose import parameters as mp",
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
