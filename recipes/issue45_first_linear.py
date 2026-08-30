"""Issue45 first-linear policy composed from reusable MOOSE/PETSc primitives."""
from __future__ import annotations

import math
from typing import Any

from qpx_harness.moose import log as moose_log
from qpx_harness.moose import parameters as mp
from qpx_harness.petsc import jacobian as jac
from qpx_harness.petsc import ksp
from qpx_harness.petsc import log as petsc_log
from qpx_harness.petsc import options as po

ISSUE = 45
TARGET = 1.0e16
DIAGNOSTIC_NL_MAX_ITS = 1
JACOBIAN_REL_TOL = 1.0e-6
FIRST_LINEAR_PETSC_OPTIONS = (
    "-snes_test_jacobian",
    "-ksp_view",
    "-ksp_monitor_true_residual",
)
REQUIRED_EXISTING_OPTIONS = ("-snes_converged_reason", "-ksp_converged_reason")
COUPLED_SCALING_VARIABLES = ("n_e", "potential_plasma")


class Issue45FirstLinearError(RuntimeError):
    pass


def instrument_first_linear(text: str) -> tuple[str, dict[str, Any]]:
    out = mp.upsert_parameter(
        text,
        "Executioner",
        "nl_max_its",
        str(DIAGNOSTIC_NL_MAX_ITS),
    )
    out = po.add_flags(out, REQUIRED_EXISTING_OPTIONS + FIRST_LINEAR_PETSC_OPTIONS)
    return out, {
        "target": TARGET,
        "diagnostic_nl_max_its": DIAGNOSTIC_NL_MAX_ITS,
        "petsc_options_added": list(FIRST_LINEAR_PETSC_OPTIONS),
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "diagnostic_horizon_changed": True,
    }


def _jacobian_analysis(text: str) -> dict[str, Any]:
    tests = jac.parse_comparisons(text)
    if not tests:
        return {
            "status": "HOLD",
            "class": "JACOBIAN_EVIDENCE_INSUFFICIENT",
            "reason": "PETSc -snes_test_jacobian produced no parseable Jacobian comparison",
            "relative_tolerance": JACOBIAN_REL_TOL,
            "tests": [],
        }
    nonfinite = [
        item
        for item in tests
        if not math.isfinite(item["relative_frobenius_error"])
        or not math.isfinite(item["absolute_frobenius_error"])
    ]
    finite_rel = [
        item["relative_frobenius_error"]
        for item in tests
        if math.isfinite(item["relative_frobenius_error"])
    ]
    worst = max(finite_rel) if finite_rel else math.inf
    if nonfinite or worst > JACOBIAN_REL_TOL:
        return {
            "status": "HOLD",
            "class": "JACOBIAN_MISMATCH",
            "reason": (
                "assembled-vs-finite-difference Jacobian relative Frobenius error exceeds "
                f"the declared tolerance {JACOBIAN_REL_TOL:g} or is non-finite"
            ),
            "relative_tolerance": JACOBIAN_REL_TOL,
            "worst_relative_frobenius_error": worst,
            "nonfinite": nonfinite,
            "tests": tests,
        }
    return {
        "status": "PASS",
        "class": "JACOBIAN_CORRECTNESS_PASS",
        "reason": "all observed PETSc Jacobian comparisons satisfy the declared relative tolerance",
        "relative_tolerance": JACOBIAN_REL_TOL,
        "worst_relative_frobenius_error": worst,
        "nonfinite": [],
        "tests": tests,
    }


def _first_failed_reason(rows: list[dict[str, Any]]) -> str | None:
    return next((str(row["reason"]) for row in rows if not row.get("converged")), None)


def _runtime_core(text: str, *, returncode: int) -> dict[str, Any]:
    residual_blocks = moose_log.parse_variable_residual_norms(text)
    scaling_blocks = moose_log.parse_automatic_scaling_factors(text)
    scaling = scaling_blocks[0] if scaling_blocks else {}
    linear_reason = _first_failed_reason(petsc_log.parse_linear_solve_terminations(text))
    nonlinear_reason = _first_failed_reason(petsc_log.parse_nonlinear_solve_terminations(text))
    pc_failure_reason = petsc_log.parse_pc_failure_reason(text)

    pc_hits = petsc_log.line_hits(
        text,
        (
            r"DIVERGED_PC_FAILED",
            r"DIVERGED_PCSETUP_FAILED",
            r"PC failed due to",
            r"zero pivot",
            r"factorization",
            r"PCSetUp.*fail",
        ),
    )
    factorization_hits = petsc_log.line_hits(
        text,
        (
            r"FACTOR_(?:NUMERIC|STRUCT)_ZEROPIVOT",
            r"zero pivot",
            r"factorization",
            r"MatFactor",
            r"PCSetUp.*fail",
        ),
    )

    nonfinite_residuals: list[dict[str, Any]] = []
    for index, block in enumerate(residual_blocks):
        for name, value in block.items():
            if not math.isfinite(value):
                nonfinite_residuals.append(
                    {"block": index, "variable": name, "value": repr(value)}
                )

    scaling_invalid: list[dict[str, Any]] = []
    for name in COUPLED_SCALING_VARIABLES:
        if name not in scaling:
            continue
        value = scaling[name]
        if not math.isfinite(value) or value == 0.0:
            scaling_invalid.append({"variable": name, "value": repr(value)})

    selected_scaling = [
        abs(scaling[name])
        for name in COUPLED_SCALING_VARIABLES
        if name in scaling and math.isfinite(scaling[name]) and scaling[name] != 0.0
    ]
    scaling_ratio = (
        max(selected_scaling) / min(selected_scaling)
        if len(selected_scaling) == 2
        else None
    )

    finite_residual_blocks = bool(residual_blocks) and not nonfinite_residuals
    if pc_hits or linear_reason in {"DIVERGED_PC_FAILED", "DIVERGED_PCSETUP_FAILED"}:
        decision_class = "PC_OR_FACTORIZATION_FAIL"
        if pc_failure_reason == "FACTOR_NUMERIC_ZEROPIVOT":
            reason = (
                "PETSc LU/preconditioner setup failed with FACTOR_NUMERIC_ZEROPIVOT; "
                "later nonlinear NAN/INF is downstream of the factorization failure"
            )
        else:
            reason = (
                "the first direct linear-solver signature is PETSc preconditioner/setup failure; "
                "later nonlinear NAN/INF is not promoted above that earlier failure"
            )
    elif nonfinite_residuals:
        decision_class = "INITIAL_NONFINITE_FAIL"
        reason = "variable-residual diagnostics contain NaN/Inf without an earlier PC failure"
    elif scaling_invalid:
        decision_class = "SCALING_DOMINATED_FAIL"
        reason = "automatic scaling produced a zero or non-finite factor for a coupled variable"
    elif returncode != 0 and finite_residual_blocks:
        decision_class = "COUPLED_JACOBIAN_OR_RESIDUAL_FAIL"
        reason = (
            "runtime failed with finite per-variable residual evidence and without a direct "
            "PC/non-finite/scaling-invalid signature"
        )
    else:
        decision_class = "DIAGNOSTIC_INSUFFICIENT"
        reason = "available diagnostic signatures do not uniquely identify H1-H4"

    return {
        "class": decision_class,
        "reason": reason,
        "returncode": returncode,
        "linear_reason": linear_reason,
        "nonlinear_reason": nonlinear_reason,
        "pc_failure_reason": pc_failure_reason,
        "pc_hits": pc_hits,
        "factorization_hits": factorization_hits,
        "variable_residuals": residual_blocks,
        "nonfinite_residuals": nonfinite_residuals,
        "automatic_scaling_factors": scaling_blocks,
        "scaling_invalid": scaling_invalid,
        "scaling_factor_ratio_n_e_to_potential": scaling_ratio,
    }


def _first_linear_termination(text: str) -> dict[str, Any] | None:
    rows = petsc_log.parse_linear_solve_terminations(text)
    return dict(rows[0]) if rows else None


def analyze_first_linear_text(text: str, *, returncode: int) -> dict[str, Any]:
    jacobian = _jacobian_analysis(text)
    core = _runtime_core(text, returncode=returncode)
    identity = ksp.parse_ksp_view(text)
    true_rows = ksp.parse_true_residuals(text)
    linear = _first_linear_termination(text)

    def result(status: str, klass: str, reason: str, **extra: Any) -> dict[str, Any]:
        return {
            "status": status,
            "class": klass,
            "reason": reason,
            "jacobian": jacobian,
            "ksp_identity": identity,
            "true_residuals": true_rows,
            "first_linear": linear,
            "core": core,
            **extra,
        }

    if jacobian.get("class") == "JACOBIAN_MISMATCH":
        return result(
            "HOLD",
            "JACOBIAN_MISMATCH",
            "the augmented constrained Jacobian exceeds the declared assembled-vs-FD tolerance",
        )
    pc_failure = (
        core.get("pc_failure_reason")
        or (
            linear is not None
            and linear.get("reason")
            in {"DIVERGED_PC_FAILED", "DIVERGED_PCSETUP_FAILED"}
        )
        or bool(
            petsc_log.line_hits(
                text,
                (
                    r"FACTOR_(?:NUMERIC|STRUCT)_ZEROPIVOT",
                    r"PC failed due to",
                    r"zero pivot",
                ),
            )
        )
    )
    if pc_failure:
        return result(
            "HOLD",
            "PC_OR_FACTORIZATION_FAIL",
            "the first-linear diagnostic exposes a PETSc PC/factorization failure signature",
        )
    if core.get("nonfinite_residuals") or core.get("nonlinear_reason") == "DIVERGED_FUNCTION_NANORINF":
        return result(
            "HOLD",
            "NONFINITE_FAIL",
            "the first-linear diagnostic contains non-finite residual/function evidence",
        )
    complete = (
        jacobian.get("status") == "PASS"
        and identity.get("ksp_type") is not None
        and identity.get("pc_type") is not None
        and bool(true_rows)
        and linear is not None
    )
    if not complete:
        return result(
            "HOLD",
            "DIAGNOSTIC_INSUFFICIENT",
            "Jacobian, KSP identity, true-residual, and first-linear evidence are not all observable",
        )

    restart = identity.get("restart")
    iterations = int(linear["iterations"]) if linear.get("iterations") is not None else 0
    aligned = (
        identity["ksp_type"] == "gmres"
        and isinstance(restart, int)
        and restart > 0
        and iterations > 0
        and iterations % restart == 0
    )
    finite_true = all(
        math.isfinite(row["true_residual"])
        and math.isfinite(row["relative_true_residual"])
        for row in true_rows
    )
    if linear["reason"] == "DIVERGED_BREAKDOWN" and aligned and finite_true:
        return result(
            "PASS",
            "GMRES_RESTART_BREAKDOWN",
            "the augmented Jacobian passes the assembled-vs-FD gate and the effective GMRES solve reaches DIVERGED_BREAKDOWN at a restart boundary with finite true-residual evidence",
            restart_aligned=True,
        )
    if linear["converged"]:
        return result(
            "HOLD",
            "FIRST_LINEAR_BEHAVIOR_CHANGED",
            "the bounded C0 first linear solve converged instead of reproducing the historical breakdown",
            restart_aligned=aligned,
        )
    return result(
        "HOLD",
        "DIAGNOSTIC_INSUFFICIENT",
        "the observed linear failure does not satisfy the predeclared GMRES-restart discriminator",
        restart_aligned=aligned,
    )
