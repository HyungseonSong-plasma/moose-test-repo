"""Synthetic characterization for the canonical inventory first-linear diagnostic."""
from __future__ import annotations

from recipes import issue45_first_linear as first_linear_recipe

from qpx_harness.adapters.moose.electron_inventory.closure_model import _synthetic_constrained_input
from qpx_harness.analysis.electron_inventory.first_linear_stats import build_first_linear_stats
from qpx_harness.analysis.electron_inventory.first_linear_structure import audit_first_linear_structure

TARGET = first_linear_recipe.TARGET
instrument_first_linear = first_linear_recipe.instrument_first_linear
analyze_first_linear_text = first_linear_recipe.analyze_first_linear_text


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


def self_test() -> int:
    try:
        base = _synthetic_constrained_input(TARGET)
        diagnostic, _ = instrument_first_linear(base)
        if audit_first_linear_structure(base, diagnostic)["status"] != "PASS":
            raise AssertionError("positive first-linear structure did not pass")

        mutated = diagnostic.replace("boundary = outlet", "boundary = plasma_cover", 1)
        if audit_first_linear_structure(base, mutated)["status"] == "PASS":
            raise AssertionError("non-diagnostic physics mutation was accepted")
        decision = analyze_first_linear_text(_synthetic_log(), returncode=1)
        if decision["class"] != "KSP_BREAKDOWN_RESIDUAL_FIDELITY_LOSS":
            raise AssertionError("KSP residual-fidelity breakdown did not classify")
        residual_audit = decision.get("ksp_residual_audit", {})
        if not residual_audit.get("residual_fidelity_loss_observed"):
            raise AssertionError("reported-vs-true residual separation was not detected")
        if residual_audit.get("max_residual_separation_ratio", 0.0) < 1.0e6:
            raise AssertionError("residual separation magnitude was not preserved")
        if not decision.get("restart_boundary_observed"):
            raise AssertionError("restart-boundary chronology was not preserved")
        if decision.get("restart_causality") != "NOT_ESTABLISHED":
            raise AssertionError("restart boundary was promoted to causal evidence")

        stats = build_first_linear_stats(
            "issue45-first-linear-selftest",
            runtime={"returncode": 1, "wall_seconds": 0.25},
            decision=decision,
        )
        if (
            stats.common.case_id != "issue45-first-linear-selftest"
            or stats.common.return_code != 1
            or stats.common.wall_time_seconds != 0.25
            or stats.convergence is None
            or stats.convergence.solver is None
            or stats.convergence.solver.linear_solver != "gmres"
            or stats.convergence.solver.linear_restart != 30
            or stats.convergence.solver.preconditioner != "lu"
            or not stats.convergence.terminations
            or stats.convergence.terminations[0].reason != "DIVERGED_BREAKDOWN"
            or stats.convergence.terminations[0].iteration_count != 30
            or stats.accuracy is None
            or not stats.accuracy.matrix_errors
            or stats.accuracy.matrix_errors[0].error.relative_error != 2.0e-9
            or stats.accuracy.matrix_errors[0].error.absolute_error != 2.0e-8
        ):
            raise AssertionError("first-linear Stats mapping contract drifted")
        if not any(
            sample.kind == "petsc_true" and sample.iteration == 30
            for sample in stats.convergence.residuals
        ):
            raise AssertionError("true-residual facts were not preserved in Stats")
        if not any(
            sample.kind == "moose_variable_l2" and sample.variable == "n_e"
            for sample in stats.convergence.residuals
        ):
            raise AssertionError("variable-residual facts were not preserved in Stats")
        if hasattr(stats, "decision") or hasattr(stats, "evidence"):
            raise AssertionError("policy/evidence leaked into Stats")
        print("ISSUE45_FIRST_LINEAR_STATS_MAPPING_SELFTEST: PASS")

        if (
            analyze_first_linear_text(_synthetic_log(1.0e-3), returncode=1)["class"]
            != "JACOBIAN_MISMATCH"
        ):
            raise AssertionError("Jacobian mismatch mutation was not detected")

        pc_fail = _synthetic_log().replace(
            "Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30",
            "Linear solve did not converge due to DIVERGED_PC_FAILED iterations 0\n"
            "PC failed due to FACTOR_NUMERIC_ZEROPIVOT",
            1,
        )
        if (
            analyze_first_linear_text(pc_fail, returncode=1)["class"]
            != "PC_OR_FACTORIZATION_FAIL"
        ):
            raise AssertionError("PC/factorization mutation was not detected")

        nonfinite = _synthetic_log().replace(
            "n_e:                  5.0e-16",
            "n_e:                  nan",
            1,
        )
        if (
            analyze_first_linear_text(nonfinite, returncode=1)["class"]
            != "NONFINITE_FAIL"
        ):
            raise AssertionError("non-finite mutation was not detected")

        missing_view = _synthetic_log().split("KSP Object:", 1)[0]
        if (
            analyze_first_linear_text(missing_view, returncode=1)["class"]
            != "DIAGNOSTIC_INSUFFICIENT"
        ):
            raise AssertionError("missing KSP identity was over-classified")

        low_separation = _synthetic_log().replace(
            "1.0e-12 true resid norm 2.0e-03",
            "1.0e-03 true resid norm 2.0e-03",
            1,
        )
        low_decision = analyze_first_linear_text(low_separation, returncode=1)
        if low_decision["class"] != "KSP_BREAKDOWN_WITHOUT_RESIDUAL_FIDELITY_LOSS":
            raise AssertionError("low residual separation was over-classified")
    except Exception as exc:
        print(f"ISSUE45_FIRST_LINEAR_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE45_FIRST_LINEAR_SELFTEST: PASS")
    return 0
