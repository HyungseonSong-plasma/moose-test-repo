#!/usr/bin/env python3
"""WP-2 characterization for issue-agnostic log/Jacobian/KSP parsers."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import fast_plasma_coupling_diagnostic as issue43
from qpx_harness.moose import log as moose_log
from qpx_harness.petsc import jacobian as petsc_jacobian
from qpx_harness.petsc import ksp as petsc_ksp
from qpx_harness.petsc import log as petsc_log


def _diagnostic_log() -> str:
    return """Automatic scaling factors:
 species_a: 1e-4
 phi: 2

 |residual|_2 of individual variables:
 species_a: 8e-03
 phi: 6e-03
---------- Testing Jacobian -------------
||J - Jfd||_F/||J||_F = 2.1e-09, ||J - Jfd||_F = 2.3e-08
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


def _pc_failure_log() -> str:
    return """Linear solve did not converge due to DIVERGED_PC_FAILED iterations 0
PC failed due to FACTOR_NUMERIC_ZEROPIVOT
Nonlinear solve did not converge due to DIVERGED_FUNCTION_NANORINF iterations 0
"""


def _check_moose_log_parsers() -> None:
    text = _diagnostic_log()
    if moose_log.parse_variable_residual_norms(text) != issue43._parse_variable_residuals(text):
        raise AssertionError("variable residual parser drift")
    if moose_log.parse_automatic_scaling_factors(text) != issue43._parse_scaling_factors(text):
        raise AssertionError("automatic scaling parser drift")


def _check_petsc_log_parsers() -> None:
    text = _pc_failure_log()
    if petsc_log.parse_pc_failure_reason(text) != issue43._parse_pc_failure_reason(text):
        raise AssertionError("PC failure parser drift")
    linear = petsc_log.parse_linear_solve_terminations(text)
    if not linear or linear[0]["reason"] != "DIVERGED_PC_FAILED":
        raise AssertionError("linear termination parser missed DIVERGED_PC_FAILED")
    nonlinear = petsc_log.parse_nonlinear_solve_terminations(text)
    if not nonlinear or nonlinear[0]["reason"] != "DIVERGED_FUNCTION_NANORINF":
        raise AssertionError("nonlinear termination parser missed DIVERGED_FUNCTION_NANORINF")


def _check_ksp_parsers() -> None:
    text = _diagnostic_log()
    expected_true = [
        {
            "iteration": 0,
            "reported_residual": 8.0e-3,
            "true_residual": 8.0e-3,
            "relative_true_residual": 1.0,
        },
        {
            "iteration": 30,
            "reported_residual": 1.0e-12,
            "true_residual": 2.0e-3,
            "relative_true_residual": 2.5e-1,
        },
    ]
    if petsc_ksp.parse_true_residuals(text) != expected_true:
        raise AssertionError("true-residual parser drift")

    expected_identity = {"ksp_type": "gmres", "restart": 30, "pc_type": "lu"}
    if petsc_ksp.parse_ksp_view(text) != expected_identity:
        raise AssertionError("KSP-view parser drift")

    parsed = petsc_log.parse_linear_solve_terminations(text)
    expected_first = {
        "converged": False,
        "reason": "DIVERGED_BREAKDOWN",
        "iterations": 30,
    }
    if not parsed or parsed[0] != expected_first:
        raise AssertionError("first-linear termination parser drift")


def _check_jacobian_parser() -> None:
    text = _diagnostic_log()
    expected = issue43._parse_jacobian_tests(text)
    observed = petsc_jacobian.parse_comparisons(text)
    if observed != expected:
        raise AssertionError("Jacobian comparison parser drift")
    if petsc_jacobian.parse_comparisons("no jacobian report\n") != []:
        raise AssertionError("missing Jacobian evidence was invented")


def _check_boundaries() -> None:
    reusable = (
        "qpx_harness/moose/log.py",
        "qpx_harness/petsc/log.py",
        "qpx_harness/petsc/ksp.py",
        "qpx_harness/petsc/jacobian.py",
    )
    forbidden = (
        "ISSUE =",
        "n_e",
        "potential_plasma",
        "r45_inventory_lambda",
        "JACOBIAN_MISMATCH",
        "GMRES_RESTART_BREAKDOWN",
        "FD_REFERENCE_QUANTIZATION_CONFIRMED",
        "recipes.",
    )
    for rel in reusable:
        source = (ROOT / rel).read_text()
        for token in forbidden:
            if token in source:
                raise AssertionError(f"special-case/policy semantic leaked into {rel}: {token}")


def main() -> int:
    try:
        _check_moose_log_parsers()
        print("ISSUE48_WP2_CHECK: moose-log-parsers=PASS")
        _check_petsc_log_parsers()
        print("ISSUE48_WP2_CHECK: petsc-termination-parsers=PASS")
        _check_ksp_parsers()
        print("ISSUE48_WP2_CHECK: ksp-view-and-true-residual=PASS")
        _check_jacobian_parser()
        print("ISSUE48_WP2_CHECK: jacobian-facts=PASS")
        _check_boundaries()
        print("ISSUE48_WP2_CHECK: parser-policy-boundary=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP2_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP2_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
