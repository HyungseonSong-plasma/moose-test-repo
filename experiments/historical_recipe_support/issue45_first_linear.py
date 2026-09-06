"""Issue45 first-linear policy with spec-backed instrumentation and reusable diagnostics."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from qpx_harness.reasoning import diagnose_coupled_runtime_evidence
from qpx_harness.reasoning.jacobian import diagnose_jacobian_evidence
from qpx_harness.evidence import (
    extract_jacobian_evidence,
    first_failed_reason,
    first_linear_termination,
    runtime_core_facts,
)
from qpx_harness.adapters.moose import parameters as mp
from qpx_harness.petsc import ksp
from qpx_harness.petsc import log as petsc_log
from qpx_harness.petsc import options as po
from qpx_harness.adapters.moose.mutation_spec import compile_mutation_spec, load_mutation_json_file
from qpx_harness.adapters.moose.mutation_spec.plan import MutationCasePlan, MutationPlan
from qpx_harness.adapters.moose.transforms import TransformError, apply_case_plan

ISSUE = 45
TARGET = 1.0e16
JACOBIAN_REL_TOL = 1.0e-6
RESIDUAL_FIDELITY_RATIO_THRESHOLD = 1.0e6
COUPLED_SCALING_VARIABLES = ("n_e", "potential_plasma")

SPEC_PATH = (
    Path(__file__).resolve().parents[2]
    / "qpx_harness"
    / "specs"
    / "experiments"
    / "issue45_first_linear.json"
)


class Issue45FirstLinearError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _execution_plan() -> MutationPlan:
    return compile_mutation_spec(load_mutation_json_file(SPEC_PATH))


def _case() -> MutationCasePlan:
    return _execution_plan().case("first_linear")


def _parameter_value(name: str) -> str:
    values = [
        operation.argument_dict().get("value")
        for operation in _case().operations
        if operation.op == "set_parameter"
        and operation.argument_dict().get("path") == "Executioner"
        and operation.argument_dict().get("name") == name
    ]
    if len(values) != 1 or not isinstance(values[0], str):
        raise RuntimeError(f"invalid Issue45 first-linear parameter plan for {name!r}")
    return values[0]


def _flag_groups() -> tuple[tuple[str, ...], ...]:
    groups: list[tuple[str, ...]] = []
    for operation in _case().operations:
        if operation.op != "add_petsc_flags":
            continue
        flags = operation.argument_dict().get("flags")
        if not isinstance(flags, tuple) or not all(isinstance(flag, str) for flag in flags):
            raise RuntimeError("invalid Issue45 first-linear PETSc flag plan")
        groups.append(flags)
    if len(groups) != 2:
        raise RuntimeError(f"expected two Issue45 PETSc flag groups, found {len(groups)}")
    return tuple(groups)


DIAGNOSTIC_NL_MAX_ITS = int(_parameter_value("nl_max_its"))
REQUIRED_EXISTING_OPTIONS, FIRST_LINEAR_PETSC_OPTIONS = _flag_groups()


def _raise_legacy_compatible(exc: TransformError) -> None:
    cause = exc.__cause__
    if isinstance(cause, (mp.MooseParameterError, po.PetscOptionsError)):
        raise cause
    raise Issue45FirstLinearError(str(exc)) from exc


def instrument_first_linear(text: str) -> tuple[str, dict[str, Any]]:
    try:
        out = apply_case_plan(text, _case())
    except TransformError as exc:
        _raise_legacy_compatible(exc)
        raise AssertionError("unreachable")
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
    return diagnose_jacobian_evidence(
        extract_jacobian_evidence(text),
        relative_tolerance=JACOBIAN_REL_TOL,
    )


def _first_failed_reason(rows: list[dict[str, Any]]) -> str | None:
    return first_failed_reason(rows)


def _runtime_core(text: str, *, returncode: int) -> dict[str, Any]:
    facts = runtime_core_facts(
        text,
        returncode=returncode,
        coupled_scaling_variables=COUPLED_SCALING_VARIABLES,
    )
    diagnosis = diagnose_coupled_runtime_evidence(facts)
    decision_class = diagnosis["class"]

    if decision_class == "PC_OR_FACTORIZATION_FAIL":
        if facts["pc_failure_reason"] == "FACTOR_NUMERIC_ZEROPIVOT":
            reason = (
                "PETSc LU/preconditioner setup failed with FACTOR_NUMERIC_ZEROPIVOT; "
                "later nonlinear NAN/INF is downstream of the factorization failure"
            )
        else:
            reason = (
                "the first direct linear-solver signature is PETSc preconditioner/setup failure; "
                "later nonlinear NAN/INF is not promoted above that earlier failure"
            )
    elif decision_class == "INITIAL_NONFINITE_FAIL":
        reason = "variable-residual diagnostics contain NaN/Inf without an earlier PC failure"
    elif decision_class == "SCALING_DOMINATED_FAIL":
        reason = "automatic scaling produced a zero or non-finite factor for a coupled variable"
    elif decision_class == "COUPLED_JACOBIAN_OR_RESIDUAL_FAIL":
        reason = (
            "runtime failed with finite per-variable residual evidence and without a direct "
            "PC/non-finite/scaling-invalid signature"
        )
    else:
        reason = "available diagnostic signatures do not uniquely identify H1-H4"

    return {
        "class": decision_class,
        "reason": reason,
        "returncode": returncode,
        "linear_reason": facts["linear_reason"],
        "nonlinear_reason": facts["nonlinear_reason"],
        "pc_failure_reason": facts["pc_failure_reason"],
        "pc_hits": facts["pc_hits"],
        "factorization_hits": facts["factorization_hits"],
        "variable_residuals": facts["variable_residuals"],
        "nonfinite_residuals": facts["nonfinite_residuals"],
        "automatic_scaling_factors": facts["automatic_scaling_factors"],
        "scaling_invalid": facts["scaling_invalid"],
        "scaling_factor_ratio_n_e_to_potential": facts["scaling_factor_ratio"],
    }


def _first_linear_termination(text: str) -> dict[str, Any] | None:
    return first_linear_termination(text)


def analyze_first_linear_text(text: str, *, returncode: int) -> dict[str, Any]:
    jacobian = _jacobian_analysis(text)
    core = _runtime_core(text, returncode=returncode)
    identity = ksp.parse_ksp_view(text)
    true_rows = ksp.parse_true_residuals(text)
    linear = _first_linear_termination(text)
    residual_audit = ksp.residual_fidelity_audit(
        true_rows,
        restart=identity.get("restart"),
        ratio_threshold=RESIDUAL_FIDELITY_RATIO_THRESHOLD,
    )

    def result(status: str, klass: str, reason: str, **extra: Any) -> dict[str, Any]:
        return {
            "status": status,
            "class": klass,
            "reason": reason,
            "jacobian": jacobian,
            "ksp_identity": identity,
            "true_residuals": true_rows,
            "ksp_residual_audit": residual_audit,
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
    restart_boundary_observed = (
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
    if linear["reason"] == "DIVERGED_BREAKDOWN" and finite_true:
        if residual_audit["residual_fidelity_loss_observed"]:
            return result(
                "PASS",
                "KSP_BREAKDOWN_RESIDUAL_FIDELITY_LOSS",
                "the augmented Jacobian passes the assembled-vs-FD gate while KSP reaches "
                "DIVERGED_BREAKDOWN with a large separation between reported and true "
                "residuals; any coincident GMRES restart boundary is retained as chronology, "
                "not established causality",
                restart_boundary_observed=restart_boundary_observed,
                restart_causality="NOT_ESTABLISHED",
            )
        return result(
            "PASS",
            "KSP_BREAKDOWN_WITHOUT_RESIDUAL_FIDELITY_LOSS",
            "the augmented Jacobian passes the assembled-vs-FD gate and KSP reaches "
            "DIVERGED_BREAKDOWN without the predeclared reported-vs-true residual "
            "separation threshold",
            restart_boundary_observed=restart_boundary_observed,
            restart_causality="NOT_ESTABLISHED",
        )
    if linear["converged"]:
        return result(
            "HOLD",
            "FIRST_LINEAR_BEHAVIOR_CHANGED",
            "the bounded C0 first linear solve converged instead of reproducing the historical breakdown",
            restart_boundary_observed=restart_boundary_observed,
            restart_causality="NOT_ESTABLISHED",
        )
    return result(
        "HOLD",
        "DIAGNOSTIC_INSUFFICIENT",
        "the observed linear behavior is neither a converged first solve nor a sufficiently observed DIVERGED_BREAKDOWN",
        restart_boundary_observed=restart_boundary_observed,
        restart_causality="NOT_ESTABLISHED",
    )
