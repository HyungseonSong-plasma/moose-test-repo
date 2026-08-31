#!/usr/bin/env python3
"""P0 behavior characterization for the canonical Issue45 first-linear recipe."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import electron_inventory_nullspace as inv
from qpx_harness.moose import parameters as mp
from qpx_harness.petsc import options as po
from recipes import issue45_first_linear as recipe


def _synthetic_log(jac_rel: float = 2.0e-9) -> str:
    return f"""---------- Testing Jacobian -------------
||J - Jfd||_F/||J||_F = {jac_rel:.12e}, ||J - Jfd||_F = 2.0e-08
    |residual|_2 of individual variables:
       n_e:                  5.0e-16
       potential_plasma:     8.0e-03
       r45_inventory_lambda: 0
  0 KSP preconditioned resid norm 8.0e-03 true resid norm 8.0e-03 ||r(i)||/||b|| 1.0e+00
 30 KSP preconditioned resid norm 1.0e-12 true resid norm 2.0e-03 ||r(i)||/||b|| 2.5e-01
Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30
KSP Object: 1 MPI process
  type: gmres
    restart=30, using modified Gram-Schmidt orthogonalization
  maximum iterations=10000, initial guess is zero
  left preconditioning
  using PRECONDITIONED norm type for convergence test
PC Object: 1 MPI process
  type: lu
    out-of-place factorization
Nonlinear solve did not converge due to DIVERGED_MAX_IT iterations 1
"""


def _check_construction() -> None:
    base = inv._synthetic_constrained_input(recipe.TARGET)
    text, meta = recipe.instrument_first_linear(base)

    closure = inv.audit_constrained_quasisteady_structure(
        text,
        expected_macro_avg=recipe.TARGET,
    )
    if closure["status"] != "PASS":
        raise AssertionError("first-linear construction no longer preserves C0 closure")

    nl_max = mp.unquote(mp.get_parameter(text, "Executioner", "nl_max_its"))
    if nl_max != str(recipe.DIAGNOSTIC_NL_MAX_ITS):
        raise AssertionError(f"first-linear nonlinear horizon drifted: {nl_max}")

    expected_flags = list(recipe.REQUIRED_EXISTING_OPTIONS + recipe.FIRST_LINEAR_PETSC_OPTIONS)
    observed_flags = po.get_flags(text)
    if observed_flags != expected_flags:
        raise AssertionError(
            f"first-linear PETSc option contract drifted: {observed_flags} != {expected_flags}"
        )

    expected_meta = {
        "target": recipe.TARGET,
        "diagnostic_nl_max_its": recipe.DIAGNOSTIC_NL_MAX_ITS,
        "petsc_options_added": list(recipe.FIRST_LINEAR_PETSC_OPTIONS),
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "diagnostic_horizon_changed": True,
    }
    if meta != expected_meta:
        raise AssertionError(f"first-linear metadata drift: {meta!r}")


def _check_analysis_positive() -> None:
    result = recipe.analyze_first_linear_text(_synthetic_log(), returncode=1)
    if result.get("status") != "PASS" or result.get("class") != "GMRES_RESTART_BREAKDOWN":
        raise AssertionError(f"positive first-linear class drifted: {result!r}")
    if result.get("ksp_identity") != {"ksp_type": "gmres", "restart": 30, "pc_type": "lu"}:
        raise AssertionError("positive KSP identity drifted")
    if len(result.get("true_residuals") or []) != 2:
        raise AssertionError("positive true-residual evidence drifted")


def _check_analysis_negative_controls() -> None:
    base = _synthetic_log()
    cases = {
        "jacobian-mismatch": (
            _synthetic_log(1.0e-3),
            "JACOBIAN_MISMATCH",
        ),
        "pc-failure": (
            base.replace(
                "Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30",
                "Linear solve did not converge due to DIVERGED_PC_FAILED iterations 0\n"
                "PC failed due to FACTOR_NUMERIC_ZEROPIVOT",
                1,
            ),
            "PC_OR_FACTORIZATION_FAIL",
        ),
        "nonfinite": (
            base.replace("n_e:                  5.0e-16", "n_e:                  nan", 1),
            "NONFINITE_FAIL",
        ),
        "missing-ksp-view": (
            base.split("KSP Object:", 1)[0],
            "DIAGNOSTIC_INSUFFICIENT",
        ),
        "restart-misaligned": (
            base.replace(
                "DIVERGED_BREAKDOWN iterations 30",
                "DIVERGED_BREAKDOWN iterations 29",
                1,
            ),
            "DIAGNOSTIC_INSUFFICIENT",
        ),
        "linear-converged": (
            base.replace(
                "Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30",
                "Linear solve converged due to CONVERGED_RTOL iterations 17",
                1,
            ),
            "FIRST_LINEAR_BEHAVIOR_CHANGED",
        ),
    }

    for name, (text, expected_class) in cases.items():
        result = recipe.analyze_first_linear_text(text, returncode=1)
        if result.get("class") != expected_class:
            raise AssertionError(
                f"{name} classification drift: {result.get('class')} != {expected_class}"
            )
        if result.get("status") == "PASS":
            raise AssertionError(f"negative control unexpectedly passed: {name}")


def _check_primitive_usage() -> None:
    source = (ROOT / "recipes" / "issue45_first_linear.py").read_text()
    required = (
        "from qpx_harness.moose import log as moose_log",
        "from qpx_harness.moose import parameters as mp",
        "from qpx_harness.petsc import jacobian as jac",
        "from qpx_harness.petsc import ksp",
        "from qpx_harness.petsc import log as petsc_log",
        "from qpx_harness.petsc import options as po",
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"recipe does not use expected generic primitive: {token}")

    forbidden = (
        "electron_inventory_nullspace",
        "petsc_first_linear_diagnostic",
        "fast_plasma_coupling_diagnostic",
        "augmented_jacobian_localization",
        "jacobian_fd_reference_audit",
    )
    for token in forbidden:
        if token in source:
            raise AssertionError(f"reverse dependency leaked into Issue45 recipe: {token}")


def main() -> int:
    try:
        _check_construction()
        print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHECK: construction=PASS")
        _check_analysis_positive()
        print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHECK: positive-analysis=PASS")
        _check_analysis_negative_controls()
        print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHECK: negative-controls=PASS")
        _check_primitive_usage()
        print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHECK: recipe-reverse-dependency=NONE")
    except Exception as exc:
        print(f"ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
