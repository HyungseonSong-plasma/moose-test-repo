"""Issue45 closed-electron and constrained-closure structural audits."""
from __future__ import annotations

import math
import re
from typing import Any

from ..moose_input import MooseInput, MooseInputError
from ..preflight import validate_parser_symbols_text
from .constants import (
    CONSTRAINT_TYPE,
    DRIFT_TYPE,
    EXPECTED_CONSTRAINED_ELECTRON_KERNEL_TYPES,
    EXPECTED_DRIFT_BOUNDARIES,
    EXPECTED_POISSON_GROUNDS,
    EXPECTED_TRANSIENT_ELECTRON_KERNEL_TYPES,
    LAMBDA_VARIABLE,
    MACRO_AVG_POSTPROCESSOR,
)
from .errors import ElectronInventoryNullspaceError


def _unquote(value: str | None) -> str | None:
    if value is None:
        return None
    result = value.strip()
    if len(result) >= 2 and result[0] == result[-1] and result[0] in {"'", '"'}:
        result = result[1:-1]
    return result.strip()


def _words(value: str | None) -> list[str]:
    raw = _unquote(value)
    return raw.split() if raw else []


def _parameter_value(text: str, path: str, name: str) -> str | None:
    doc = MooseInput(text)
    span = doc.unique(path)
    block = text[span.start : span.end]
    pattern = re.compile(
        rf"(?m)^\s*{re.escape(name)}\s*=\s*(?P<value>[^#\r\n]*?)\s*(?:#.*)?$"
    )
    matches = list(pattern.finditer(block))
    if len(matches) > 1:
        raise ElectronInventoryNullspaceError(
            f"ambiguous parameter {path}/{name}: {len(matches)} assignments"
        )
    return matches[0].group("value").strip() if matches else None


def _parameter_count(text: str, path: str, name: str) -> int:
    doc = MooseInput(text)
    span = doc.unique(path)
    block = text[span.start : span.end]
    return len(re.findall(rf"(?m)^\s*{re.escape(name)}\s*=", block))


def _set_or_insert_parameter(text: str, path: str, name: str, value: str) -> str:
    count = _parameter_count(text, path, name)
    if count > 1:
        raise ElectronInventoryNullspaceError(
            f"ambiguous parameter {path}/{name}: {count} assignments"
        )
    try:
        if count == 1:
            return MooseInput(text).replace_parameters(path, {name: value})[0]
        return MooseInput(text).insert_before_close(path, f"  {name} = {value}")[0]
    except MooseInputError as exc:
        raise ElectronInventoryNullspaceError(
            f"failed to set {path}/{name}: {exc}"
        ) from exc


def _direct_children(text: str, parent: str) -> list[str]:
    depth = parent.count("/") + 1
    prefix = parent + "/"
    return sorted(
        block.path
        for block in MooseInput(text).blocks
        if block.path.startswith(prefix) and block.path.count("/") == depth
    )


def _truthy(value: str | None) -> bool:
    raw = (_unquote(value) or "").lower()
    return raw in {"1", "true", "yes", "on"}


def _ensure_debug_block(text: str) -> str:
    blocks = MooseInput(text).find("Debug")
    if len(blocks) > 1:
        raise ElectronInventoryNullspaceError("multiple top-level [Debug] blocks")
    if not blocks:
        suffix = "" if text.endswith("\n") else "\n"
        text = text + suffix + "\n[Debug]\n  show_var_residual_norms = true\n[]\n"
        MooseInput(text)
        return text
    return _set_or_insert_parameter(text, "Debug", "show_var_residual_norms", "true")


def _electron_kernel_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in _direct_children(text, "FVKernels"):
        if _unquote(_parameter_value(text, path, "variable")) != "n_e":
            continue
        records.append(
            {"path": path, "type": _unquote(_parameter_value(text, path, "type"))}
        )
    return records


def _electron_fvbcs(text: str) -> list[dict[str, Any]]:
    if not MooseInput(text).find("FVBCs"):
        return []
    return [
        {"path": path, "type": _unquote(_parameter_value(text, path, "type"))}
        for path in _direct_children(text, "FVBCs")
        if _unquote(_parameter_value(text, path, "variable")) == "n_e"
    ]


def _poisson_fvbcs(text: str) -> list[dict[str, Any]]:
    if not MooseInput(text).find("FVBCs"):
        return []
    result: list[dict[str, Any]] = []
    for path in _direct_children(text, "FVBCs"):
        if _unquote(_parameter_value(text, path, "variable")) != "potential_plasma":
            continue
        result.append(
            {
                "path": path,
                "boundary": _words(_parameter_value(text, path, "boundary")),
                "value": _unquote(_parameter_value(text, path, "value")),
            }
        )
    return result


def _flux_boundary_audit(
    text: str, electron_kernels: list[dict[str, Any]], add: Any
) -> None:
    drift_paths = [item["path"] for item in electron_kernels if item["type"] == DRIFT_TYPE]
    diffusion_paths = [
        item["path"] for item in electron_kernels if item["type"] == "FVDiffusion"
    ]
    add("one-electrostatic-drift", len(drift_paths) == 1, drift_paths, 1)
    add("one-electron-diffusion", len(diffusion_paths) == 1, diffusion_paths, 1)

    drift_boundaries: set[str] = set()
    drift_forced: list[str] = []
    drift_force_all = False
    if len(drift_paths) == 1:
        drift = drift_paths[0]
        drift_boundaries = set(_words(_parameter_value(text, drift, "boundaries_to_avoid")))
        drift_forced = _words(_parameter_value(text, drift, "boundaries_to_force"))
        drift_force_all = _truthy(_parameter_value(text, drift, "force_boundary_execution"))
    add(
        "drift-closes-all-plasma-boundaries",
        drift_boundaries == set(EXPECTED_DRIFT_BOUNDARIES),
        sorted(drift_boundaries),
        sorted(EXPECTED_DRIFT_BOUNDARIES),
    )
    add("drift-no-forced-boundaries", not drift_forced, drift_forced, [])
    add("drift-no-force-all-boundaries", not drift_force_all, drift_force_all, False)

    diffusion_forced: list[dict[str, Any]] = []
    for path in diffusion_paths:
        forced = _words(_parameter_value(text, path, "boundaries_to_force"))
        force_all = _truthy(_parameter_value(text, path, "force_boundary_execution"))
        if forced or force_all:
            diffusion_forced.append(
                {
                    "path": path,
                    "boundaries_to_force": forced,
                    "force_boundary_execution": force_all,
                }
            )
    add("diffusion-natural-boundary-path", not diffusion_forced, diffusion_forced, [])


def _audit_poisson_grounding(text: str, add: Any) -> None:
    bcs = _poisson_fvbcs(text)
    boundaries = {boundary for item in bcs for boundary in item["boundary"]}
    all_zero = bool(bcs) and all(item["value"] in {"0", "0.0"} for item in bcs)
    add(
        "poisson-ground-boundary-set",
        boundaries == set(EXPECTED_POISSON_GROUNDS),
        sorted(boundaries),
        sorted(EXPECTED_POISSON_GROUNDS),
    )
    add("poisson-ground-values-zero", all_zero, bcs, "all potential grounds = 0")


def audit_closed_electron_structure(text: str) -> dict[str, Any]:
    """Audit prerequisites for the exact transient-model inventory invariant."""
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
    electron_kernels = _electron_kernel_records(text)
    observed_types = sorted(item["type"] for item in electron_kernels if item["type"])
    expected_types = sorted(EXPECTED_TRANSIENT_ELECTRON_KERNEL_TYPES)
    add(
        "electron-kernel-set",
        observed_types == expected_types and len(electron_kernels) == 3,
        electron_kernels,
        expected_types,
    )
    _flux_boundary_audit(text, electron_kernels, add)
    electron_bcs = _electron_fvbcs(text)
    add("no-electron-fvbc", not electron_bcs, electron_bcs, [])
    _audit_poisson_grounding(text, add)

    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": "CLOSED_SOURCE_FREE_ELECTRON_STRUCTURE_PASS" if not blockers else "CONSERVATION_STRUCTURE_FAIL",
        "checks": checks,
        "blockers": blockers,
        "electron_kernels": electron_kernels,
        "electron_fvbcs": electron_bcs,
        "derivation_scope": "steady spatial n_e residual only; transient FVTimeKernel excluded from the nullspace identity",
    }


def _float_parameter(text: str, path: str, name: str) -> float | None:
    raw = _unquote(_parameter_value(text, path, name))
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def audit_constrained_quasisteady_structure(
    text: str, *, expected_macro_avg: float
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

    parser_errors = validate_parser_symbols_text(text, "<issue45-closure-audit>")
    add("parser-symbol-preflight", not parser_errors, parser_errors, [])
    electron_kernels = _electron_kernel_records(text)
    observed_types = sorted(item["type"] for item in electron_kernels if item["type"])
    expected_types = sorted(EXPECTED_CONSTRAINED_ELECTRON_KERNEL_TYPES)
    add(
        "quasisteady-electron-kernel-set",
        observed_types == expected_types and len(electron_kernels) == 3,
        electron_kernels,
        expected_types,
    )
    add("fvtimekernel-removed", "FVTimeKernel" not in observed_types, observed_types, "no FVTimeKernel")
    _flux_boundary_audit(text, electron_kernels, add)
    electron_bcs = _electron_fvbcs(text)
    add("no-electron-fvbc", not electron_bcs, electron_bcs, [])
    _audit_poisson_grounding(text, add)

    lambda_paths = [
        path for path in _direct_children(text, "Variables")
        if path.split("/")[-1] == LAMBDA_VARIABLE
    ]
    lambda_type = _unquote(_parameter_value(text, lambda_paths[0], "type")) if len(lambda_paths) == 1 else None
    add("one-scalar-lagrange-multiplier", len(lambda_paths) == 1, lambda_paths, 1)
    add("scalar-lagrange-multiplier-type", lambda_type == "MooseVariableScalar", lambda_type, "MooseVariableScalar")

    constraint_paths = [item["path"] for item in electron_kernels if item["type"] == CONSTRAINT_TYPE]
    add("one-inventory-constraint", len(constraint_paths) == 1, constraint_paths, 1)
    constraint_lambda = None
    constraint_phi0 = None
    constraint_block: list[str] = []
    if len(constraint_paths) == 1:
        path = constraint_paths[0]
        constraint_lambda = _unquote(_parameter_value(text, path, "lambda"))
        constraint_phi0 = _unquote(_parameter_value(text, path, "phi0"))
        constraint_block = _words(_parameter_value(text, path, "block"))
    add("constraint-couples-scalar-lambda", constraint_lambda == LAMBDA_VARIABLE, constraint_lambda, LAMBDA_VARIABLE)
    add("constraint-uses-macro-average-postprocessor", constraint_phi0 == MACRO_AVG_POSTPROCESSOR, constraint_phi0, MACRO_AVG_POSTPROCESSOR)
    add("constraint-block-is-plasma", constraint_block == ["plasma"], constraint_block, ["plasma"])

    pp_paths = [
        path for path in _direct_children(text, "Postprocessors")
        if path.split("/")[-1] == MACRO_AVG_POSTPROCESSOR
    ]
    pp_type = _unquote(_parameter_value(text, pp_paths[0], "type")) if len(pp_paths) == 1 else None
    pp_value = _float_parameter(text, pp_paths[0], "value") if len(pp_paths) == 1 else None
    target_tol = max(abs(expected_macro_avg) * 1e-12, 1e-300)
    add("one-macro-average-provider", len(pp_paths) == 1, pp_paths, 1)
    add("macro-average-provider-type", pp_type == "ConstantPostprocessor", pp_type, "ConstantPostprocessor")
    add(
        "macro-average-target-preserved",
        pp_value is not None and math.isfinite(pp_value) and abs(pp_value - expected_macro_avg) <= target_tol,
        pp_value,
        expected_macro_avg,
    )

    executioner_type = _unquote(_parameter_value(text, "Executioner", "type"))
    add("steady-executioner", executioner_type == "Steady", executioner_type, "Steady")
    inames = _words(_parameter_value(text, "Executioner", "petsc_options_iname"))
    values = _words(_parameter_value(text, "Executioner", "petsc_options_value"))
    add(
        "lm-saddle-factorization-contract",
        "-pc_factor_shift_type" in inames and "NONZERO" in values,
        {"petsc_options_iname": inames, "petsc_options_value": values},
        {"petsc_options_iname": "-pc_factor_shift_type", "petsc_options_value": "NONZERO"},
    )
    execute_on = _words(_parameter_value(text, "Outputs/out", "execute_on"))
    add("final-csv-observation", execute_on == ["FINAL"], execute_on, ["FINAL"])
    debug = _parameter_value(text, "Debug", "show_var_residual_norms") if MooseInput(text).find("Debug") else None
    all_norms = _parameter_value(text, "Outputs/console", "all_variable_norms")
    add("runtime-variable-residual-observability", debug == "true", debug, "true")
    add("runtime-console-variable-norms", all_norms == "true", all_norms, "true")

    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": "CONSTRAINED_QUASISTEADY_STRUCTURE_PASS" if not blockers else "CLOSURE_STRUCTURE_FAIL",
        "checks": checks,
        "blockers": blockers,
        "electron_kernels": electron_kernels,
        "electron_fvbcs": electron_bcs,
        "constraint": {
            "type": CONSTRAINT_TYPE,
            "lambda": constraint_lambda,
            "phi0": constraint_phi0,
            "target_macro_average": expected_macro_avg,
        },
        "physics_interpretation": "phi0 fixes the inherited macrostate electron average; the scalar Lagrange multiplier closes the singular inventory direction without reintroducing physical time dependence",
    }
