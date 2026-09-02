"""Construction and P1 structure owner for Issue43 coupling diagnostics."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from recipes import issue43_coupling_diagnostic as recipe
from recipes import issue43_feedback_basis as feedback_basis

from ..execution import cases as case_ops
from .. import execution_contract as ec
from .. import issue43_fast_output_contract as output_contract
from ..moose import output_observation as ooc
from ..moose import blocks as mb
from ..moose import parameters as mp
from ..moose.input import MooseInputError
from ..petsc import options as po
from ..moose.preflight import validate_parser_symbols_text
from .constants import (
    DIAGNOSTIC_PETSC_OPTIONS,
    JACOBIAN_PETSC_OPTIONS,
    RUNTIME_PURGE_DIRECTORY_NAMES,
    RUNTIME_PURGE_PATTERNS,
    STEPS,
    FastPlasmaCouplingDiagnosticError,
)


def instrument_input(
    input_text: str, *, jacobian_test: bool = False
) -> tuple[str, dict[str, Any]]:
    """Apply the canonical Issue43 diagnostic recipe."""
    try:
        return recipe.instrument_input(input_text, jacobian_test=jacobian_test)
    except (
        mb.MooseBlockError,
        mp.MooseParameterError,
        po.PetscOptionsError,
        MooseInputError,
    ) as exc:
        raise FastPlasmaCouplingDiagnosticError(str(exc)) from exc


def _stage_case(source: Path, target: Path, input_text: str) -> list[str]:
    try:
        case_ops.stage_case(
            source,
            target,
            input_text=input_text,
            purge_directory_names=RUNTIME_PURGE_DIRECTORY_NAMES,
            purge_patterns=RUNTIME_PURGE_PATTERNS,
        )
        refs = case_ops.validate_case_references(target)
    except case_ops.CaseError as exc:
        raise FastPlasmaCouplingDiagnosticError(f"case staging failed: {exc}") from exc
    return [ref["resolved"] for ref in refs]


def _parameter_value(text: str, path: str, name: str) -> str | None:
    try:
        return mp.unquote(mp.get_parameter(text, path, name))
    except mp.MooseParameterError as exc:
        raise FastPlasmaCouplingDiagnosticError(str(exc)) from exc


def _contains_petsc_options(text: str, required: tuple[str, ...]) -> bool:
    try:
        options = po.get_flags(text)
    except po.PetscOptionsError as exc:
        raise FastPlasmaCouplingDiagnosticError(str(exc)) from exc
    return all(option in options for option in required)


def _build_case(
    base_text: str, *, dt: float, radial_span: float, jacobian_test: bool = False
) -> tuple[str, dict[str, Any]]:
    uninstrumented, feedback_meta = feedback_basis.build_closed_feedback_input(
        base_text,
        dt=dt,
        steps=STEPS,
        radial_span=radial_span,
    )
    instrumented, instrumentation = instrument_input(
        uninstrumented, jacobian_test=jacobian_test
    )
    return instrumented, {
        "dt": dt,
        "steps": STEPS,
        "jacobian_test": jacobian_test,
        "feedback_basis": feedback_meta,
        "instrumentation": instrumentation,
    }


def _p1_case(
    case_id: str, text: str, *, dt: float, jacobian_test: bool = False
) -> dict[str, Any]:
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

    parser_errors = validate_parser_symbols_text(text, f"<{case_id}>")
    add("parser-symbol-preflight", not parser_errors, parser_errors, [])

    contract = output_contract._augment_execution_contract(case_id, text)
    contract_decision = ec.evaluate_contract(contract, phase="P1")
    add(
        "execution-contract-p1",
        contract_decision["status"] == "PASS",
        contract_decision["status"],
        "PASS",
    )

    output_report = ooc.observation_report(text, required_time_separation=dt)
    output_decision = ooc.evaluate_observation_report(output_report)
    add(
        "output-observation-p1",
        output_decision["status"] == "PASS",
        output_decision["status"],
        "PASS",
    )

    verbose = _parameter_value(text, "Executioner", "verbose")
    debug = _parameter_value(text, "Debug", "show_var_residual_norms")
    all_norms = _parameter_value(text, "Outputs/console", "all_variable_norms")
    add("diagnostic-executioner-verbose", verbose == "true", verbose, "true")
    add("diagnostic-variable-residuals", debug == "true", debug, "true")
    add("diagnostic-console-all-variable-norms", all_norms == "true", all_norms, "true")
    add(
        "diagnostic-petsc-options",
        _contains_petsc_options(text, DIAGNOSTIC_PETSC_OPTIONS),
        po.get_flags(text),
        list(DIAGNOSTIC_PETSC_OPTIONS),
    )
    if jacobian_test:
        add(
            "jacobian-petsc-test-option",
            _contains_petsc_options(text, JACOBIAN_PETSC_OPTIONS),
            po.get_flags(text),
            list(JACOBIAN_PETSC_OPTIONS),
        )

    expected_end = dt * STEPS
    dt_raw = _parameter_value(text, "Executioner", "dt")
    end_raw = _parameter_value(text, "Executioner", "end_time")
    try:
        dt_value = float(dt_raw) if dt_raw is not None else None
        end_value = float(end_raw) if end_raw is not None else None
    except ValueError:
        dt_value = None
        end_value = None
    numeric_tol = max(abs(dt) * 1.0e-12, 1.0e-300)
    add(
        "numerical-regime-dt-preserved",
        dt_value is not None and abs(dt_value - dt) <= numeric_tol,
        dt_value,
        dt,
    )
    add(
        "numerical-regime-end-time-preserved",
        end_value is not None and abs(end_value - expected_end) <= numeric_tol,
        end_value,
        expected_end,
    )

    blockers = [item for item in checks if item["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "checks": checks,
        "blockers": blockers,
        "contract": contract,
        "contract_decision": contract_decision,
        "output_report": output_report,
        "output_decision": output_decision,
    }
