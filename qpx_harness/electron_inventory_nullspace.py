"""Issue #45 electron-inventory nullspace and constrained quasi-steady closure audit.

The harness owns the static/framework nullspace proof, the constrained steady
representation, and the bounded C0/C1 runtime discriminator.  Phase boundaries
are explicit: preflight modes stop at P2; only --closure-run enters P3.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any

from . import evidence
from . import fast_plasma_coupling_diagnostic as coupling_diag
from . import fast_plasma_relaxation_v2 as v2
from . import fast_plasma_relaxation_v5 as v5
from .moose_input import MooseInput, MooseInputError
from .preflight import validate_parser_symbols_text
from .runtime import run_command, run_qpx


ISSUE = 45
DT_REFERENCE = 1.0e-13
STEPS = 1
DRIFT_TYPE = "QPXFVElectrostaticDrift"
CONSTRAINT_TYPE = "FVIntegralValueConstraint"
LAMBDA_VARIABLE = "r45_inventory_lambda"
MACRO_AVG_POSTPROCESSOR = "r45_ne_macro_avg"
DEFAULT_MACRO_ELECTRON_AVG = 1.0e16
C0_TARGET = 1.0e16
C1_TARGET = 1.01e16
CLOSURE_TARGET_REL_TOL = 1.0e-6
CLOSURE_DELTA_REL_TOL = 5.0e-4
INVENTORY_CONSISTENCY_REL_TOL = 1.0e-8

REQUIRED_FVFLUX_SCHEMA_PARAMETERS = (
    "boundaries_to_avoid",
    "boundaries_to_force",
    "force_boundary_execution",
)
REQUIRED_CONSTRAINT_SCHEMA_PARAMETERS = ("variable", "lambda", "phi0")
EXPECTED_DRIFT_BOUNDARIES = frozenset(
    {
        "inlet",
        "outlet",
        "plasma_electrode",
        "plasma_metal",
        "plasma_right",
        "plasma_cover",
        "plasma_wafer",
        "plasma_focus_ring",
    }
)
EXPECTED_POISSON_GROUNDS = frozenset(
    {
        "plasma_metal",
        "plasma_electrode",
        "plasma_right",
        "inlet",
        "outlet",
    }
)
EXPECTED_TRANSIENT_ELECTRON_KERNEL_TYPES = (
    "FVDiffusion",
    "FVTimeKernel",
    DRIFT_TYPE,
)
EXPECTED_CONSTRAINED_ELECTRON_KERNEL_TYPES = (
    "FVDiffusion",
    CONSTRAINT_TYPE,
    DRIFT_TYPE,
)
RUNTIME_COLUMNS = (
    "n_avg",
    "inventory",
    "domain_volume",
    "n_min",
    "n_max",
    "r43_phi_l2",
    "r43_phi_min",
    "r43_phi_max",
    "r43_charge_integral",
    "r43_charge_min",
    "r43_charge_max",
)


class ElectronInventoryNullspaceError(RuntimeError):
    pass


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


def _remove_block(text: str, path: str) -> str:
    span = MooseInput(text).unique(path)
    return text[: span.start] + text[span.end :]


def _replace_block(text: str, path: str, replacement: str) -> str:
    span = MooseInput(text).unique(path)
    payload = replacement.rstrip() + "\n"
    return text[: span.start] + payload + text[span.end :]


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
        "class": (
            "CLOSED_SOURCE_FREE_ELECTRON_STRUCTURE_PASS"
            if not blockers
            else "CONSERVATION_STRUCTURE_FAIL"
        ),
        "checks": checks,
        "blockers": blockers,
        "electron_kernels": electron_kernels,
        "electron_fvbcs": electron_bcs,
        "derivation_scope": (
            "steady spatial n_e residual only; transient FVTimeKernel excluded from the nullspace identity"
        ),
    }


def _extract_moose_json(text: str) -> Any:
    start_marker = "**START JSON DATA**"
    end_marker = "**END JSON DATA**"
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        raise ElectronInventoryNullspaceError("MOOSE JSON markers are missing")
    payload = text[start + len(start_marker) : end].strip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ElectronInventoryNullspaceError(f"invalid MOOSE JSON payload: {exc}") from exc


def _schema_presence_analysis(
    text: str,
    *,
    returncode: int,
    object_type: str,
    required_parameters: tuple[str, ...],
    semantic_terms: tuple[str, ...] = (),
) -> dict[str, Any]:
    if returncode != 0:
        return {
            "status": "HOLD",
            "class": "FRAMEWORK_SCHEMA_QUERY_FAIL",
            "reason": f"qpx --json-search returned {returncode}",
        }
    try:
        payload = _extract_moose_json(text)
    except ElectronInventoryNullspaceError as exc:
        return {
            "status": "HOLD",
            "class": "FRAMEWORK_SCHEMA_EVIDENCE_INSUFFICIENT",
            "reason": str(exc),
        }

    serialized = json.dumps(payload, sort_keys=True)
    lower = serialized.lower()
    object_present = object_type in serialized
    parameter_presence = {name: name in serialized for name in required_parameters}
    semantic_presence = {term: term.lower() in lower for term in semantic_terms}
    passed = object_present and all(parameter_presence.values()) and all(semantic_presence.values())
    return {
        "status": "PASS" if passed else "HOLD",
        "class": "FRAMEWORK_SCHEMA_PASS" if passed else "FRAMEWORK_SCHEMA_EVIDENCE_INSUFFICIENT",
        "object_present": object_present,
        "required_parameters": parameter_presence,
        "semantic_terms": semantic_presence,
    }


def analyze_drift_schema_text(text: str, *, returncode: int = 0) -> dict[str, Any]:
    result = _schema_presence_analysis(
        text,
        returncode=returncode,
        object_type=DRIFT_TYPE,
        required_parameters=REQUIRED_FVFLUX_SCHEMA_PARAMETERS,
        semantic_terms=("FVFluxKernel",),
    )
    if result["status"] == "PASS":
        result.update(
            {
                "class": "FVFLUX_SCHEMA_PASS",
                "reason": (
                    "QPX object schema exposes FVFluxKernel boundary-execution controls and FVFluxKernel semantics"
                ),
            }
        )
    else:
        result.setdefault(
            "reason",
            "QPX object schema did not prove all required FVFluxKernel inheritance semantics",
        )
    return result


def analyze_constraint_schema_text(text: str, *, returncode: int = 0) -> dict[str, Any]:
    result = _schema_presence_analysis(
        text,
        returncode=returncode,
        object_type=CONSTRAINT_TYPE,
        required_parameters=REQUIRED_CONSTRAINT_SCHEMA_PARAMETERS,
        semantic_terms=("Lagrange multiplier",),
    )
    if result["status"] == "PASS":
        result.update(
            {
                "class": "FV_INVENTORY_CONSTRAINT_SCHEMA_PASS",
                "reason": (
                    "QPX schema exposes the FV integral-value constraint with variable/lambda/phi0 Lagrange-multiplier coupling"
                ),
            }
        )
    else:
        result.setdefault(
            "reason",
            "QPX object schema did not prove the required FV integral-value Lagrange-multiplier contract",
        )
    return result


def _synthetic_closed_input() -> str:
    boundaries = " ".join(sorted(EXPECTED_DRIFT_BOUNDARIES))
    return f"""[Variables]
  [n_e]
    type = MooseVariableFVReal
  []
  [potential_plasma]
    type = MooseVariableFVReal
  []
[]
[FVKernels]
  [time]
    type = FVTimeKernel
    variable = n_e
  []
  [diffusion]
    type = FVDiffusion
    variable = n_e
  []
  [drift]
    type = {DRIFT_TYPE}
    variable = n_e
    boundaries_to_avoid = '{boundaries}'
  []
  [phi]
    type = FVDiffusion
    variable = potential_plasma
  []
[]
[FVBCs]
  [g0]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_metal
    value = 0
  []
  [g1]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_electrode
    value = 0
  []
  [g2]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_right
    value = 0
  []
  [g3]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = inlet
    value = 0
  []
  [g4]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = outlet
    value = 0
  []
[]
"""


def _synthetic_constrained_input(macro_avg: float = DEFAULT_MACRO_ELECTRON_AVG) -> str:
    base = _synthetic_closed_input().replace(
        "  [time]\n    type = FVTimeKernel\n    variable = n_e\n  []\n", "", 1
    )
    base, _ = MooseInput(base).insert_before_close(
        "Variables",
        f"""  [{LAMBDA_VARIABLE}]
    type = MooseVariableScalar
  []""",
    )
    base, _ = MooseInput(base).insert_before_close(
        "FVKernels",
        f"""  [inventory_constraint]
    type = {CONSTRAINT_TYPE}
    variable = n_e
    lambda = {LAMBDA_VARIABLE}
    phi0 = {MACRO_AVG_POSTPROCESSOR}
    block = plasma
  []""",
    )
    base += f"""
[Postprocessors]
  [{MACRO_AVG_POSTPROCESSOR}]
    type = ConstantPostprocessor
    value = {macro_avg:.17g}
  []
[]
[Executioner]
  type = Steady
  solve_type = NEWTON
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]
[Outputs]
  [out]
    type = CSV
    execute_on = FINAL
  []
  [console]
    type = Console
    execute_on = FINAL
    all_variable_norms = true
  []
[]
[Debug]
  show_var_residual_norms = true
[]
"""
    return base


def _build_constrained_quasisteady_input(
    base_text: str,
    *,
    radial_span: float,
    macro_avg: float,
    runtime_observability: bool = True,
) -> str:
    """Transform the accepted feedback model into the #45 constrained steady candidate."""
    text = v5._build_feedback_v5(
        base_text,
        dt=DT_REFERENCE,
        steps=STEPS,
        radial_span=radial_span,
    )
    text = _remove_block(text, "FVKernels/time")
    text, _ = MooseInput(text).insert_before_close(
        "Variables",
        f"""  [{LAMBDA_VARIABLE}]
    type = MooseVariableScalar
  []""",
    )
    text, _ = MooseInput(text).insert_before_close(
        "Postprocessors",
        f"""  [{MACRO_AVG_POSTPROCESSOR}]
    type = ConstantPostprocessor
    value = {macro_avg:.17g}
    outputs = none
  []""",
    )
    text, _ = MooseInput(text).insert_before_close(
        "FVKernels",
        f"""  [r45_inventory_constraint]
    type = {CONSTRAINT_TYPE}
    variable = n_e
    lambda = {LAMBDA_VARIABLE}
    phi0 = {MACRO_AVG_POSTPROCESSOR}
    block = plasma
  []""",
    )
    text = _replace_block(
        text,
        "Executioner",
        """[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_rel_tol = 1e-8
  nl_max_its = 30
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  compute_scaling_once = true
  verbose = true
  petsc_options = '-snes_converged_reason -ksp_converged_reason'
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]""",
    )
    text = _set_or_insert_parameter(text, "Outputs/out", "execute_on", "FINAL")
    text = _set_or_insert_parameter(text, "Outputs/console", "execute_on", "FINAL")
    if runtime_observability:
        text = _ensure_debug_block(text)
        text = _set_or_insert_parameter(
            text, "Outputs/console", "all_variable_norms", "true"
        )
    MooseInput(text)
    return text


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
    add(
        "fvtimekernel-removed",
        "FVTimeKernel" not in observed_types,
        observed_types,
        "no FVTimeKernel",
    )
    _flux_boundary_audit(text, electron_kernels, add)

    electron_bcs = _electron_fvbcs(text)
    add("no-electron-fvbc", not electron_bcs, electron_bcs, [])
    _audit_poisson_grounding(text, add)

    lambda_paths = [
        path
        for path in _direct_children(text, "Variables")
        if path.split("/")[-1] == LAMBDA_VARIABLE
    ]
    lambda_type = (
        _unquote(_parameter_value(text, lambda_paths[0], "type"))
        if len(lambda_paths) == 1
        else None
    )
    add("one-scalar-lagrange-multiplier", len(lambda_paths) == 1, lambda_paths, 1)
    add(
        "scalar-lagrange-multiplier-type",
        lambda_type == "MooseVariableScalar",
        lambda_type,
        "MooseVariableScalar",
    )

    constraint_paths = [
        item["path"] for item in electron_kernels if item["type"] == CONSTRAINT_TYPE
    ]
    add("one-inventory-constraint", len(constraint_paths) == 1, constraint_paths, 1)
    constraint_lambda = None
    constraint_phi0 = None
    constraint_block: list[str] = []
    if len(constraint_paths) == 1:
        path = constraint_paths[0]
        constraint_lambda = _unquote(_parameter_value(text, path, "lambda"))
        constraint_phi0 = _unquote(_parameter_value(text, path, "phi0"))
        constraint_block = _words(_parameter_value(text, path, "block"))
    add(
        "constraint-couples-scalar-lambda",
        constraint_lambda == LAMBDA_VARIABLE,
        constraint_lambda,
        LAMBDA_VARIABLE,
    )
    add(
        "constraint-uses-macro-average-postprocessor",
        constraint_phi0 == MACRO_AVG_POSTPROCESSOR,
        constraint_phi0,
        MACRO_AVG_POSTPROCESSOR,
    )
    add(
        "constraint-block-is-plasma",
        constraint_block == ["plasma"],
        constraint_block,
        ["plasma"],
    )

    pp_paths = [
        path
        for path in _direct_children(text, "Postprocessors")
        if path.split("/")[-1] == MACRO_AVG_POSTPROCESSOR
    ]
    pp_type = (
        _unquote(_parameter_value(text, pp_paths[0], "type"))
        if len(pp_paths) == 1
        else None
    )
    pp_value = _float_parameter(text, pp_paths[0], "value") if len(pp_paths) == 1 else None
    target_tol = max(abs(expected_macro_avg) * 1e-12, 1e-300)
    add("one-macro-average-provider", len(pp_paths) == 1, pp_paths, 1)
    add(
        "macro-average-provider-type",
        pp_type == "ConstantPostprocessor",
        pp_type,
        "ConstantPostprocessor",
    )
    add(
        "macro-average-target-preserved",
        pp_value is not None
        and math.isfinite(pp_value)
        and abs(pp_value - expected_macro_avg) <= target_tol,
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
    add(
        "final-csv-observation",
        _words(_parameter_value(text, "Outputs/out", "execute_on")) == ["FINAL"],
        _words(_parameter_value(text, "Outputs/out", "execute_on")),
        ["FINAL"],
    )
    debug = (
        _parameter_value(text, "Debug", "show_var_residual_norms")
        if MooseInput(text).find("Debug")
        else None
    )
    all_norms = _parameter_value(text, "Outputs/console", "all_variable_norms")
    add("runtime-variable-residual-observability", debug == "true", debug, "true")
    add("runtime-console-variable-norms", all_norms == "true", all_norms, "true")

    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": (
            "CONSTRAINED_QUASISTEADY_STRUCTURE_PASS"
            if not blockers
            else "CLOSURE_STRUCTURE_FAIL"
        ),
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
        "physics_interpretation": (
            "phi0 fixes the inherited macrostate electron average; the scalar Lagrange multiplier closes the singular inventory direction without reintroducing physical time dependence"
        ),
    }


def _normalized_target_text(text: str) -> str:
    path = f"Postprocessors/{MACRO_AVG_POSTPROCESSOR}"
    span = MooseInput(text).unique(path)
    block = text[span.start : span.end]
    normalized, count = re.subn(
        r"(?m)^(\s*value\s*=\s*)[^#\r\n]+",
        r"\1<TARGET>",
        block,
        count=1,
    )
    if count != 1:
        raise ElectronInventoryNullspaceError("failed to normalize macro-average target")
    return text[: span.start] + normalized + text[span.end :]


def _target_only_pair_audit(c0_text: str, c1_text: str) -> dict[str, Any]:
    equal = _normalized_target_text(c0_text) == _normalized_target_text(c1_text)
    return {
        "status": "PASS" if equal else "HOLD",
        "class": "TARGET_ONLY_PAIR_PASS" if equal else "PAIR_CONSTRUCTION_MISMATCH",
        "reason": (
            "C0/C1 inputs are byte-identical after normalizing the declared macro electron-average target"
            if equal
            else "C0/C1 differ in construction beyond the declared macro electron-average target"
        ),
    }


def _synthetic_runtime_row(target: float) -> dict[str, float]:
    volume = 0.05
    return {
        "n_avg": target,
        "inventory": target * volume,
        "domain_volume": volume,
        "n_min": target * 0.99,
        "n_max": target * 1.01,
        "r43_phi_l2": 0.08,
        "r43_phi_min": -0.7,
        "r43_phi_max": 0.05,
        "r43_charge_integral": 0.0,
        "r43_charge_min": -1.0e-8,
        "r43_charge_max": 2.0e-9,
    }


def _evaluate_runtime_case_data(
    *,
    target: float,
    returncode: int,
    converged_marker: bool,
    diagnostic: dict[str, Any],
    row: dict[str, float] | None,
) -> dict[str, Any]:
    zero_pivot = diagnostic.get("pc_failure_reason") in {
        "FACTOR_NUMERIC_ZEROPIVOT",
        "FACTOR_STRUCT_ZEROPIVOT",
    }
    nonfinite_runtime = bool(diagnostic.get("nonfinite_residuals")) or (
        diagnostic.get("nonlinear_reason") == "DIVERGED_FUNCTION_NANORINF"
    )
    if returncode != 0:
        return {
            "status": "HOLD",
            "class": (
                "SECONDARY_SINGULAR_MODE_SUSPECTED"
                if zero_pivot
                else "CONSTRAINED_STEADY_SOLVER_FAIL"
            ),
            "reason": (
                "constrained steady factorization still reports a zero pivot after explicit inventory closure"
                if zero_pivot
                else "constrained steady runtime did not solve successfully"
            ),
            "target": target,
            "returncode": returncode,
            "diagnostic": diagnostic,
        }
    if not converged_marker or nonfinite_runtime:
        return {
            "status": "HOLD",
            "class": "CLOSURE_EVIDENCE_INSUFFICIENT",
            "reason": "runtime return code was zero but finite accepted nonlinear convergence evidence is incomplete",
            "target": target,
            "returncode": returncode,
            "diagnostic": diagnostic,
        }
    residuals = diagnostic.get("variable_residuals") or []
    if not residuals:
        return {
            "status": "HOLD",
            "class": "CLOSURE_EVIDENCE_INSUFFICIENT",
            "reason": "per-variable nonlinear residual evidence is missing",
            "target": target,
            "diagnostic": diagnostic,
        }
    final_residuals = residuals[-1]
    required_residual_vars = ("n_e", "potential_plasma")
    residual_finite = all(
        name in final_residuals and math.isfinite(float(final_residuals[name]))
        for name in required_residual_vars
    )
    if not residual_finite:
        return {
            "status": "HOLD",
            "class": "CLOSURE_EVIDENCE_INSUFFICIENT",
            "reason": "final electron/Poisson per-variable residual evidence is missing or non-finite",
            "target": target,
            "diagnostic": diagnostic,
        }
    if row is None or any(name not in row for name in RUNTIME_COLUMNS):
        return {
            "status": "HOLD",
            "class": "CLOSURE_EVIDENCE_INSUFFICIENT",
            "reason": "final CSV does not contain the required closure observables",
            "target": target,
            "diagnostic": diagnostic,
        }
    if not all(math.isfinite(float(row[name])) for name in RUNTIME_COLUMNS):
        return {
            "status": "HOLD",
            "class": "CLOSURE_EVIDENCE_INSUFFICIENT",
            "reason": "one or more final closure observables are non-finite",
            "target": target,
            "diagnostic": diagnostic,
        }

    volume = float(row["domain_volume"])
    avg = float(row["n_avg"])
    inventory = float(row["inventory"])
    if volume <= 0.0 or float(row["n_min"]) <= 0.0:
        return {
            "status": "HOLD",
            "class": "CONSTRAINT_TARGET_TRACKING_FAIL",
            "reason": "constrained solution has non-positive domain volume or electron-density minimum",
            "target": target,
            "observables": row,
            "diagnostic": diagnostic,
        }

    target_inventory = target * volume
    avg_rel_error = abs(avg - target) / abs(target)
    inventory_rel_error = abs(inventory - target_inventory) / abs(target_inventory)
    aggregate_consistency_rel_error = abs(avg - inventory / volume) / max(abs(target), 1.0e-300)
    tracking_pass = (
        avg_rel_error <= CLOSURE_TARGET_REL_TOL
        and inventory_rel_error <= CLOSURE_TARGET_REL_TOL
        and aggregate_consistency_rel_error <= INVENTORY_CONSISTENCY_REL_TOL
    )
    return {
        "status": "PASS" if tracking_pass else "HOLD",
        "class": (
            "CONSTRAINED_STEADY_CASE_PASS"
            if tracking_pass
            else "CONSTRAINT_TARGET_TRACKING_FAIL"
        ),
        "reason": (
            "constrained steady solution converged and its electron average/inventory track the declared target"
            if tracking_pass
            else "constrained steady solution converged but the electron average/inventory does not satisfy the declared target contract"
        ),
        "target": target,
        "target_inventory": target_inventory,
        "target_relative_tolerance": CLOSURE_TARGET_REL_TOL,
        "inventory_consistency_relative_tolerance": INVENTORY_CONSISTENCY_REL_TOL,
        "average_relative_error": avg_rel_error,
        "inventory_relative_error": inventory_rel_error,
        "aggregate_consistency_relative_error": aggregate_consistency_rel_error,
        "observables": row,
        "final_variable_residuals": final_residuals,
        "diagnostic": diagnostic,
    }


def _evaluate_runtime_pair(
    c0: dict[str, Any], c1: dict[str, Any], *, target0: float, target1: float
) -> dict[str, Any]:
    classes = {c0.get("class"), c1.get("class")}
    if "SECONDARY_SINGULAR_MODE_SUSPECTED" in classes:
        return {
            "status": "HOLD",
            "class": "SECONDARY_SINGULAR_MODE_SUSPECTED",
            "reason": "a zero-pivot signature persists after explicit inventory closure",
        }
    if "CONSTRAINED_STEADY_SOLVER_FAIL" in classes:
        return {
            "status": "HOLD",
            "class": "CONSTRAINED_STEADY_SOLVER_FAIL",
            "reason": "at least one constrained steady target case did not solve",
        }
    if "CONSTRAINT_TARGET_TRACKING_FAIL" in classes:
        return {
            "status": "HOLD",
            "class": "CONSTRAINT_TARGET_TRACKING_FAIL",
            "reason": "at least one converged target case failed the predeclared inventory tracking contract",
        }
    if c0.get("status") != "PASS" or c1.get("status") != "PASS":
        return {
            "status": "HOLD",
            "class": "CLOSURE_EVIDENCE_INSUFFICIENT",
            "reason": "at least one target case lacks complete closure evidence",
        }

    avg0 = float(c0["observables"]["n_avg"])
    avg1 = float(c1["observables"]["n_avg"])
    requested_delta = target1 - target0
    observed_delta = avg1 - avg0
    if requested_delta == 0.0:
        raise ElectronInventoryNullspaceError("runtime target pair must have nonzero separation")
    delta_rel_error = abs(observed_delta - requested_delta) / abs(requested_delta)
    if delta_rel_error > CLOSURE_DELTA_REL_TOL:
        return {
            "status": "HOLD",
            "class": "CONSTRAINT_TARGET_TRACKING_FAIL",
            "reason": "C0/C1 observed electron-average shift does not track the requested target shift",
            "requested_delta": requested_delta,
            "observed_delta": observed_delta,
            "delta_relative_error": delta_rel_error,
            "delta_relative_tolerance": CLOSURE_DELTA_REL_TOL,
        }
    return {
        "status": "PASS",
        "class": "CONSTRAINED_QUASISTEADY_RUNTIME_PASS",
        "reason": (
            "both constrained steady target cases converge, satisfy their declared inventory targets, and the observed electron-average shift tracks the requested target shift"
        ),
        "requested_delta": requested_delta,
        "observed_delta": observed_delta,
        "delta_relative_error": delta_rel_error,
        "delta_relative_tolerance": CLOSURE_DELTA_REL_TOL,
    }


def self_test() -> int:
    try:
        base = _synthetic_closed_input()
        if audit_closed_electron_structure(base)["status"] != "PASS":
            raise AssertionError("positive closed/source-free structure did not pass")
        missing_boundary = base.replace(" plasma_wafer", "", 1)
        if audit_closed_electron_structure(missing_boundary)["status"] == "PASS":
            raise AssertionError("missing drift boundary negative mutation was accepted")
        electron_bc, _ = MooseInput(base).insert_before_close(
            "FVBCs",
            """  [electron_leak]
    type = FVDirichletBC
    variable = n_e
    boundary = plasma_metal
    value = 1e16
  []""",
        )
        if audit_closed_electron_structure(electron_bc)["status"] == "PASS":
            raise AssertionError("n_e FVBC negative mutation was accepted")
        electron_source, _ = MooseInput(base).insert_before_close(
            "FVKernels",
            """  [electron_source]
    type = FVCoupledForce
    variable = n_e
    v = potential_plasma
  []""",
        )
        if audit_closed_electron_structure(electron_source)["status"] == "PASS":
            raise AssertionError("n_e source/sink negative mutation was accepted")

        good_drift_schema = {
            DRIFT_TYPE: {
                "description": "derived FVFluxKernel object",
                "parameters": {
                    "boundaries_to_avoid": {"description": "FVFluxKernel avoid"},
                    "boundaries_to_force": {"description": "FVFluxKernel force"},
                    "force_boundary_execution": {
                        "description": "FVFluxKernel boundary execution"
                    },
                },
            }
        }
        wrapped = "**START JSON DATA**\n" + json.dumps(good_drift_schema) + "\n**END JSON DATA**\n"
        if analyze_drift_schema_text(wrapped)["status"] != "PASS":
            raise AssertionError("valid FVFluxKernel schema evidence did not pass")
        if analyze_drift_schema_text(
            wrapped.replace("boundaries_to_force", "unrelated")
        )["status"] == "PASS":
            raise AssertionError("missing FVFluxKernel schema control was accepted")
        if analyze_drift_schema_text("{}\n")["status"] == "PASS":
            raise AssertionError("missing MOOSE JSON evidence was accepted")

        constrained = _synthetic_constrained_input()
        if audit_constrained_quasisteady_structure(
            constrained, expected_macro_avg=DEFAULT_MACRO_ELECTRON_AVG
        )["status"] != "PASS":
            raise AssertionError("positive constrained quasi-steady structure did not pass")
        with_time = constrained.replace(
            "[FVKernels]\n",
            "[FVKernels]\n  [time]\n    type = FVTimeKernel\n    variable = n_e\n  []\n",
            1,
        )
        if audit_constrained_quasisteady_structure(
            with_time, expected_macro_avg=DEFAULT_MACRO_ELECTRON_AVG
        )["status"] == "PASS":
            raise AssertionError("closure candidate retaining FVTimeKernel was accepted")
        wrong_target = constrained.replace(
            f"value = {DEFAULT_MACRO_ELECTRON_AVG:.17g}", "value = 2e16", 1
        )
        if audit_constrained_quasisteady_structure(
            wrong_target, expected_macro_avg=DEFAULT_MACRO_ELECTRON_AVG
        )["status"] == "PASS":
            raise AssertionError("wrong macro electron-average target was accepted")
        missing_lambda = constrained.replace(
            f"lambda = {LAMBDA_VARIABLE}", "lambda = missing_lambda", 1
        )
        if audit_constrained_quasisteady_structure(
            missing_lambda, expected_macro_avg=DEFAULT_MACRO_ELECTRON_AVG
        )["status"] == "PASS":
            raise AssertionError("constraint with wrong lambda coupling was accepted")

        good_constraint_schema = {
            CONSTRAINT_TYPE: {
                "description": "integral value constraint using a Lagrange multiplier",
                "parameters": {
                    "variable": {},
                    "lambda": {"description": "Lagrange multiplier variable"},
                    "phi0": {"description": "target average value"},
                },
            }
        }
        constraint_wrapped = (
            "**START JSON DATA**\n"
            + json.dumps(good_constraint_schema)
            + "\n**END JSON DATA**\n"
        )
        if analyze_constraint_schema_text(constraint_wrapped)["status"] != "PASS":
            raise AssertionError("valid inventory-constraint schema evidence did not pass")
        if analyze_constraint_schema_text(
            constraint_wrapped.replace('"phi0"', '"unrelated"', 1)
        )["status"] == "PASS":
            raise AssertionError("constraint schema missing phi0 was accepted")

        c0_text = _synthetic_constrained_input(C0_TARGET)
        c1_text = _synthetic_constrained_input(C1_TARGET)
        if _target_only_pair_audit(c0_text, c1_text)["status"] != "PASS":
            raise AssertionError("target-only C0/C1 pair did not pass")
        c1_mutated = c1_text.replace("boundary = outlet", "boundary = plasma_cover", 1)
        if _target_only_pair_audit(c0_text, c1_mutated)["status"] == "PASS":
            raise AssertionError("non-target C0/C1 construction mutation was accepted")

        good_diag = {
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
        c0_eval = _evaluate_runtime_case_data(
            target=C0_TARGET,
            returncode=0,
            converged_marker=True,
            diagnostic=good_diag,
            row=_synthetic_runtime_row(C0_TARGET),
        )
        c1_eval = _evaluate_runtime_case_data(
            target=C1_TARGET,
            returncode=0,
            converged_marker=True,
            diagnostic=good_diag,
            row=_synthetic_runtime_row(C1_TARGET),
        )
        if _evaluate_runtime_pair(
            c0_eval, c1_eval, target0=C0_TARGET, target1=C1_TARGET
        )["class"] != "CONSTRAINED_QUASISTEADY_RUNTIME_PASS":
            raise AssertionError("positive C0/C1 runtime discriminator did not pass")
        bad_row = _synthetic_runtime_row(C1_TARGET)
        bad_row["n_avg"] = C1_TARGET * 1.001
        bad_row["inventory"] = bad_row["n_avg"] * bad_row["domain_volume"]
        if _evaluate_runtime_case_data(
            target=C1_TARGET,
            returncode=0,
            converged_marker=True,
            diagnostic=good_diag,
            row=bad_row,
        )["class"] != "CONSTRAINT_TARGET_TRACKING_FAIL":
            raise AssertionError("target-tracking negative control did not fail")
        zero_diag = {**good_diag, "pc_failure_reason": "FACTOR_NUMERIC_ZEROPIVOT"}
        if _evaluate_runtime_case_data(
            target=C0_TARGET,
            returncode=1,
            converged_marker=False,
            diagnostic=zero_diag,
            row=None,
        )["class"] != "SECONDARY_SINGULAR_MODE_SUSPECTED":
            raise AssertionError("secondary zero-pivot negative control was not classified")
        if _evaluate_runtime_case_data(
            target=C0_TARGET,
            returncode=0,
            converged_marker=True,
            diagnostic={**good_diag, "variable_residuals": []},
            row=_synthetic_runtime_row(C0_TARGET),
        )["class"] != "CLOSURE_EVIDENCE_INSUFFICIENT":
            raise AssertionError("missing residual evidence was over-classified")
    except Exception as exc:
        print(f"ISSUE45_INVENTORY_NULLSPACE_SELFTEST: FAIL ({exc})")
        print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE45_INVENTORY_NULLSPACE_SELFTEST: PASS")
    print("ISSUE45_INVENTORY_CLOSURE_RUNTIME_SELFTEST: PASS")
    return 0


def _base_case_context() -> tuple[Path, str, float]:
    repo_root = Path(__file__).resolve().parents[1]
    base_case = repo_root / v2.v1.BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise ElectronInventoryNullspaceError(f"missing accepted electron control: {base_case}")
    mesh = v2.mesh_stats(base_case / "qvt.msh")
    radial_span = float(mesh["bbox_span_m"]["x"])
    return base_case, (base_case / "input.i").read_text(), radial_span


def _evidence_root(*, exe: Path, results_root: str | None, stem: str) -> Path:
    root_parent = (
        Path(results_root).expanduser().resolve()
        if results_root
        else exe.parent / "temp" / "results"
    )
    return evidence.ensure_fresh_directory(
        root_parent / f"{stem}_{evidence.utc_timestamp()}"
    )


def _prepare_case(*, exe: Path, results_root: str | None) -> dict[str, Any]:
    base_case, base_text, radial_span = _base_case_context()
    text = v5._build_feedback_v5(
        base_text,
        dt=DT_REFERENCE,
        steps=STEPS,
        radial_span=radial_span,
    )
    p1 = audit_closed_electron_structure(text)
    root = _evidence_root(
        exe=exe, results_root=results_root, stem="issue45_inventory_nullspace"
    )
    case_dir = root / "case"
    v2.v1._copy_case(base_case, case_dir, text)
    v2.v1._validate_assets(case_dir)
    return {
        "root": root,
        "case_dir": case_dir,
        "input_path": case_dir / "input.i",
        "p1": p1,
    }


def _prepare_closure_case(
    *, exe: Path, results_root: str | None, macro_avg: float
) -> dict[str, Any]:
    base_case, base_text, radial_span = _base_case_context()
    text = _build_constrained_quasisteady_input(
        base_text,
        radial_span=radial_span,
        macro_avg=macro_avg,
    )
    p1 = audit_constrained_quasisteady_structure(text, expected_macro_avg=macro_avg)
    root = _evidence_root(
        exe=exe, results_root=results_root, stem="issue45_inventory_closure"
    )
    case_dir = root / "case"
    v2.v1._copy_case(base_case, case_dir, text)
    v2.v1._validate_assets(case_dir)
    return {
        "root": root,
        "case_dir": case_dir,
        "input_path": case_dir / "input.i",
        "p1": p1,
        "macro_electron_average": macro_avg,
    }


def _prepare_closure_runtime_cases(
    *, exe: Path, results_root: str | None
) -> dict[str, Any]:
    base_case, base_text, radial_span = _base_case_context()
    root = _evidence_root(
        exe=exe,
        results_root=results_root,
        stem="issue45_inventory_closure_runtime",
    )
    cases: dict[str, Any] = {}
    for label, target in (("C0_reference", C0_TARGET), ("C1_shift", C1_TARGET)):
        text = _build_constrained_quasisteady_input(
            base_text,
            radial_span=radial_span,
            macro_avg=target,
            runtime_observability=True,
        )
        p1 = audit_constrained_quasisteady_structure(text, expected_macro_avg=target)
        case_dir = root / "cases" / label
        v2.v1._copy_case(base_case, case_dir, text)
        v2.v1._validate_assets(case_dir)
        cases[label] = {
            "target": target,
            "text": text,
            "case_dir": case_dir,
            "input_path": case_dir / "input.i",
            "p1": p1,
        }
    pair = _target_only_pair_audit(
        cases["C0_reference"]["text"], cases["C1_shift"]["text"]
    )
    return {"root": root, "cases": cases, "pair": pair}


def _run_p2_check_input(
    *, exe: Path, prepared: dict[str, Any], log_path: Path | None = None
) -> dict[str, Any]:
    actual_log = log_path or (prepared["root"] / "p2_check_input.log")
    run = run_qpx(
        exe,
        cwd=prepared["case_dir"],
        input_name="input.i",
        log_path=actual_log,
        extra_args=("--check-input", "--color", "off"),
        stream=False,
    )
    return {
        "status": "PASS" if run.returncode == 0 else "HOLD",
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(actual_log),
        "failure": v5._classify_p2_failure(actual_log, run.returncode),
        "identity": {
            **evidence.identity_record(executable=exe, input_path=prepared["input_path"]),
            "qpx_sha256": evidence.sha256_file(exe),
        },
    }


def _run_schema_query(
    *,
    exe: Path,
    prepared: dict[str, Any],
    object_type: str,
    analyzer: Any,
    log_name: str,
) -> dict[str, Any]:
    log_path = prepared["root"] / log_name
    run = run_command(
        [str(exe), "--json-search", object_type],
        cwd=prepared["case_dir"],
        log_path=log_path,
        stream=False,
    )
    analysis = analyzer(
        log_path.read_text(errors="replace") if log_path.is_file() else "",
        returncode=run.returncode,
    )
    return {
        **analysis,
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(log_path),
        "qpx_realpath": str(exe),
        "qpx_sha256": evidence.sha256_file(exe),
    }


def run_preflight(*, qpx: str | None, results_root: str | None) -> int:
    exe = v2.resolve_executable(qpx)
    v2.validate_executable(exe)
    prepared = _prepare_case(exe=exe, results_root=results_root)
    p1_pass = prepared["p1"]["status"] == "PASS"
    check_input = _run_p2_check_input(exe=exe, prepared=prepared) if p1_pass else {}
    schema = (
        _run_schema_query(
            exe=exe,
            prepared=prepared,
            object_type=DRIFT_TYPE,
            analyzer=analyze_drift_schema_text,
            log_name="p2_drift_schema.log",
        )
        if p1_pass
        else {}
    )
    p2_check_pass = check_input.get("status") == "PASS"
    p2_schema_pass = schema.get("status") == "PASS"
    status = "PASS" if p1_pass and p2_check_pass and p2_schema_pass else "HOLD"
    decision = {
        "status": status,
        "class": (
            "INVENTORY_LEFT_NULLSPACE_STATIC_PASS"
            if status == "PASS"
            else "CONSERVATION_STRUCTURE_FAIL"
            if not p1_pass
            else schema.get("class", "HARNESS_OR_CONSTRUCTION_FAIL")
            if not p2_schema_pass
            else "HARNESS_OR_CONSTRUCTION_FAIL"
        ),
        "reason": (
            "the generated closed/source-free electron residual satisfies the structural conservation contract, and user-local QPX schema confirms the custom drift exposes FVFluxKernel conservative boundary-execution semantics"
            if status == "PASS"
            else "P0/P1/P2 did not complete the static/framework conservation chain"
        ),
        "left_null_vector": "[1^T, 0]" if status == "PASS" else None,
        "identity": (
            "[1^T,0] J_steady = 0 for the current reduced closed/source-free model"
            if status == "PASS"
            else None
        ),
        "p3_required_for_this_identity": False,
    }
    summary_path = prepared["root"] / "summary.json"
    v2._write_json(
        summary_path,
        {
            "issue": ISSUE,
            "mode": "inventory-nullspace-preflight",
            "status": status,
            "p3_executed": False,
            "claim": (
                "static/framework proof of the electron-inventory left-null identity for the current closed/source-free reduced model"
            ),
            "p1": prepared["p1"],
            "p2": {"check_input": check_input, "drift_schema": schema},
            "decision": decision,
        },
    )
    print(f"ISSUE45_INVENTORY_NULLSPACE_P1: {'PASS' if p1_pass else 'HOLD'}")
    print(
        f"ISSUE45_INVENTORY_NULLSPACE_P2_CHECK_INPUT: "
        f"{'PASS' if p2_check_pass else 'HOLD'}"
    )
    print(
        f"ISSUE45_INVENTORY_NULLSPACE_P2_DRIFT_SCHEMA: "
        f"{'PASS' if p2_schema_pass else 'HOLD'}"
    )
    print(f"ISSUE45_INVENTORY_NULLSPACE_PREFLIGHT: {status}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_CLASS: {decision['class']}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_REASON: {decision['reason']}")
    print(f"ISSUE45_INVENTORY_NULLSPACE_SUMMARY: {summary_path}")
    return 0 if status == "PASS" else 2


def run_closure_preflight(
    *, qpx: str | None, results_root: str | None, macro_avg: float
) -> int:
    if not math.isfinite(macro_avg) or macro_avg <= 0.0:
        raise ElectronInventoryNullspaceError("macro electron average must be finite and positive")
    exe = v2.resolve_executable(qpx)
    v2.validate_executable(exe)
    prepared = _prepare_closure_case(
        exe=exe, results_root=results_root, macro_avg=macro_avg
    )
    p1_pass = prepared["p1"]["status"] == "PASS"
    check_input = _run_p2_check_input(exe=exe, prepared=prepared) if p1_pass else {}
    schema = (
        _run_schema_query(
            exe=exe,
            prepared=prepared,
            object_type=CONSTRAINT_TYPE,
            analyzer=analyze_constraint_schema_text,
            log_name="p2_constraint_schema.log",
        )
        if p1_pass
        else {}
    )
    p2_check_pass = check_input.get("status") == "PASS"
    p2_schema_pass = schema.get("status") == "PASS"
    status = "PASS" if p1_pass and p2_check_pass and p2_schema_pass else "HOLD"
    decision = {
        "status": status,
        "class": (
            "CONSTRAINED_QUASISTEADY_CLOSURE_READY"
            if status == "PASS"
            else "CLOSURE_STRUCTURE_FAIL"
            if not p1_pass
            else schema.get("class", "HARNESS_OR_CONSTRUCTION_FAIL")
            if not p2_schema_pass
            else "HARNESS_OR_CONSTRUCTION_FAIL"
        ),
        "reason": (
            "the generated steady electron-Poisson candidate removes FVTimeKernel, adds one scalar Lagrange multiplier, and uses FVIntegralValueConstraint to preserve the declared macrostate electron average while QPX accepts the input and exposes the required constraint schema"
            if status == "PASS"
            else "P0/P1/P2 did not complete the constrained quasi-steady closure representation chain"
        ),
        "physical_constraint": "integral_Omega n_e dV = V_plasma * n_e_macro_avg",
        "macro_electron_average": macro_avg,
        "p3_executed": False,
        "p3_authorized": False,
    }
    summary_path = prepared["root"] / "summary.json"
    v2._write_json(
        summary_path,
        {
            "issue": ISSUE,
            "mode": "inventory-closure-preflight",
            "status": status,
            "p3_executed": False,
            "claim": (
                "construction/framework readiness of the physically derived constrained quasi-steady electron-Poisson closure"
            ),
            "macro_electron_average": macro_avg,
            "p1": prepared["p1"],
            "p2": {"check_input": check_input, "constraint_schema": schema},
            "decision": decision,
        },
    )
    print(f"ISSUE45_INVENTORY_CLOSURE_P1: {'PASS' if p1_pass else 'HOLD'}")
    print(
        f"ISSUE45_INVENTORY_CLOSURE_P2_CHECK_INPUT: "
        f"{'PASS' if p2_check_pass else 'HOLD'}"
    )
    print(
        f"ISSUE45_INVENTORY_CLOSURE_P2_CONSTRAINT_SCHEMA: "
        f"{'PASS' if p2_schema_pass else 'HOLD'}"
    )
    print(f"ISSUE45_INVENTORY_CLOSURE_PREFLIGHT: {status}")
    print(f"ISSUE45_INVENTORY_CLOSURE_CLASS: {decision['class']}")
    print(f"ISSUE45_INVENTORY_CLOSURE_REASON: {decision['reason']}")
    print(f"ISSUE45_INVENTORY_CLOSURE_SUMMARY: {summary_path}")
    return 0 if status == "PASS" else 2


def _closure_runtime_preflight_result(
    *, qpx: str | None, results_root: str | None
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any], str]:
    exe = v2.resolve_executable(qpx)
    v2.validate_executable(exe)
    prepared = _prepare_closure_runtime_cases(exe=exe, results_root=results_root)
    p1_pass = all(
        case["p1"]["status"] == "PASS" for case in prepared["cases"].values()
    )
    pair_pass = prepared["pair"]["status"] == "PASS"
    p2: dict[str, Any] = {}
    if p1_pass and pair_pass:
        for label, case in prepared["cases"].items():
            p2[label] = _run_p2_check_input(
                exe=exe,
                prepared={"root": prepared["root"], **case},
                log_path=prepared["root"] / f"p2_{label}.log",
            )
    p2_pass = bool(p2) and all(item["status"] == "PASS" for item in p2.values())
    c0 = prepared["cases"]["C0_reference"]
    schema = (
        _run_schema_query(
            exe=exe,
            prepared={"root": prepared["root"], **c0},
            object_type=CONSTRAINT_TYPE,
            analyzer=analyze_constraint_schema_text,
            log_name="p2_constraint_schema.log",
        )
        if p1_pass and pair_pass
        else {}
    )
    schema_pass = schema.get("status") == "PASS"
    status = "PASS" if p1_pass and pair_pass and p2_pass and schema_pass else "HOLD"
    return exe, prepared, p2, schema, status


def _emit_closure_runtime_preflight_markers(
    *,
    prepared: dict[str, Any],
    p2: dict[str, Any],
    schema: dict[str, Any],
    status: str,
    summary_path: Path,
) -> None:
    for label in ("C0_reference", "C1_shift"):
        print(
            f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_P1_{label}: "
            f"{prepared['cases'][label]['p1']['status']}"
        )
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_P1_PAIR: {prepared['pair']['status']}")
    for label in ("C0_reference", "C1_shift"):
        print(
            f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_P2_{label}: "
            f"{p2.get(label, {}).get('status', 'HOLD')}"
        )
    print(
        "ISSUE45_INVENTORY_CLOSURE_RUNTIME_P2_CONSTRAINT_SCHEMA: "
        + schema.get("status", "HOLD")
    )
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_PREFLIGHT: {status}")
    print(
        "ISSUE45_INVENTORY_CLOSURE_RUNTIME_CLASS: "
        + (
            "CLOSURE_RUNTIME_BATCH_READY"
            if status == "PASS"
            else "HARNESS_OR_CONSTRUCTION_FAIL"
        )
    )
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_SUMMARY: {summary_path}")


def run_closure_runtime_preflight(*, qpx: str | None, results_root: str | None) -> int:
    _, prepared, p2, schema, status = _closure_runtime_preflight_result(
        qpx=qpx, results_root=results_root
    )
    summary_path = prepared["root"] / "summary.json"
    v2._write_json(
        summary_path,
        {
            "issue": ISSUE,
            "mode": "inventory-closure-runtime-preflight",
            "status": status,
            "p3_executed": False,
            "p3_authorized_by_harness": False,
            "targets": {"C0_reference": C0_TARGET, "C1_shift": C1_TARGET},
            "acceptance": {
                "target_relative_tolerance": CLOSURE_TARGET_REL_TOL,
                "delta_relative_tolerance": CLOSURE_DELTA_REL_TOL,
                "inventory_consistency_relative_tolerance": INVENTORY_CONSISTENCY_REL_TOL,
            },
            "p1": {
                label: case["p1"] for label, case in prepared["cases"].items()
            },
            "pair_contract": prepared["pair"],
            "p2": {"check_input": p2, "constraint_schema": schema},
            "decision": {
                "status": status,
                "class": (
                    "CLOSURE_RUNTIME_BATCH_READY"
                    if status == "PASS"
                    else "HARNESS_OR_CONSTRUCTION_FAIL"
                ),
                "reason": (
                    "C0/C1 constrained steady cases pass structural equivalence, user-local check-input, and constraint-schema gates"
                    if status == "PASS"
                    else "C0/C1 runtime batch did not pass all P0/P1/P2 construction gates"
                ),
            },
        },
    )
    _emit_closure_runtime_preflight_markers(
        prepared=prepared,
        p2=p2,
        schema=schema,
        status=status,
        summary_path=summary_path,
    )
    return 0 if status == "PASS" else 2


def _find_runtime_csv(case_dir: Path) -> Path:
    candidates: list[Path] = []
    for path in sorted(case_dir.glob("*.csv")):
        try:
            with path.open(newline="") as handle:
                fields = set(csv.DictReader(handle).fieldnames or ())
        except (OSError, csv.Error):
            continue
        if set(RUNTIME_COLUMNS).issubset(fields):
            candidates.append(path)
    if not candidates:
        raise ElectronInventoryNullspaceError(
            f"no runtime CSV contains the required closure observables in {case_dir}"
        )
    preferred = case_dir / "input_out.csv"
    return preferred if preferred in candidates else candidates[0]


def _read_final_runtime_row(path: Path) -> dict[str, float]:
    try:
        with path.open(newline="") as handle:
            raw_rows = list(csv.DictReader(handle))
    except (OSError, csv.Error) as exc:
        raise ElectronInventoryNullspaceError(
            f"cannot read runtime CSV {path}: {exc}"
        ) from exc
    if not raw_rows:
        raise ElectronInventoryNullspaceError(f"runtime CSV is empty: {path}")
    raw = raw_rows[-1]
    row: dict[str, float] = {}
    for name in RUNTIME_COLUMNS:
        try:
            row[name] = float(raw[name])
        except (KeyError, ValueError) as exc:
            raise ElectronInventoryNullspaceError(
                f"invalid/missing {name} in final runtime CSV row: {path}"
            ) from exc
    if LAMBDA_VARIABLE in raw:
        try:
            value = float(raw[LAMBDA_VARIABLE])
            if math.isfinite(value):
                row[LAMBDA_VARIABLE] = value
        except (TypeError, ValueError):
            pass
    return row


def _runtime_case(
    *, exe: Path, case: dict[str, Any], root: Path, label: str
) -> dict[str, Any]:
    log_path = root / f"p3_{label}.log"
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_CASE_START: {label}")
    run = run_qpx(
        exe,
        cwd=case["case_dir"],
        input_name="input.i",
        log_path=log_path,
        extra_args=("--color", "off"),
        stream=True,
    )
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_CASE_END: {label} rc={run.returncode}")
    log_text = log_path.read_text(errors="replace") if log_path.is_file() else ""
    diagnostic = coupling_diag.analyze_log_text(log_text, returncode=run.returncode)
    converged_marker = (
        "Solve Converged!" in log_text
        or "Nonlinear solve converged due to" in log_text
    )
    row = None
    csv_path = None
    if run.returncode == 0:
        try:
            csv_path = _find_runtime_csv(case["case_dir"])
            row = _read_final_runtime_row(csv_path)
        except ElectronInventoryNullspaceError:
            row = None
    evaluation = _evaluate_runtime_case_data(
        target=float(case["target"]),
        returncode=run.returncode,
        converged_marker=converged_marker,
        diagnostic=diagnostic,
        row=row,
    )
    return {
        "target": case["target"],
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(log_path),
        "csv": str(csv_path) if csv_path else None,
        "input_identity": {
            **evidence.identity_record(executable=exe, input_path=case["input_path"]),
            "qpx_sha256": evidence.sha256_file(exe),
        },
        "diagnostic": diagnostic,
        "evaluation": evaluation,
    }


def run_closure_runtime(*, qpx: str | None, results_root: str | None) -> int:
    exe, prepared, p2, schema, preflight_status = _closure_runtime_preflight_result(
        qpx=qpx, results_root=results_root
    )
    summary_path = prepared["root"] / "summary.json"
    if preflight_status != "PASS":
        v2._write_json(
            summary_path,
            {
                "issue": ISSUE,
                "mode": "inventory-closure-runtime",
                "status": "HOLD",
                "class": "HARNESS_OR_CONSTRUCTION_FAIL",
                "p3_executed": False,
                "p1": {
                    label: case["p1"] for label, case in prepared["cases"].items()
                },
                "pair_contract": prepared["pair"],
                "p2": {"check_input": p2, "constraint_schema": schema},
            },
        )
        _emit_closure_runtime_preflight_markers(
            prepared=prepared,
            p2=p2,
            schema=schema,
            status="HOLD",
            summary_path=summary_path,
        )
        return 2

    print("ISSUE45_INVENTORY_CLOSURE_RUNTIME_PREFLIGHT: PASS")
    runtime = {
        label: _runtime_case(
            exe=exe,
            case=prepared["cases"][label],
            root=prepared["root"],
            label=label,
        )
        for label in ("C0_reference", "C1_shift")
    }
    c0 = runtime["C0_reference"]["evaluation"]
    c1 = runtime["C1_shift"]["evaluation"]
    decision = _evaluate_runtime_pair(c0, c1, target0=C0_TARGET, target1=C1_TARGET)
    v2._write_json(
        summary_path,
        {
            "issue": ISSUE,
            "mode": "inventory-closure-runtime",
            "status": decision["status"],
            "class": decision["class"],
            "p3_executed": True,
            "evr_count_for_this_batch": 1,
            "scope": (
                "one bounded two-target constrained steady discriminator for the current closed/source-free reduced electron-Poisson model"
            ),
            "targets": {"C0_reference": C0_TARGET, "C1_shift": C1_TARGET},
            "acceptance": {
                "target_relative_tolerance": CLOSURE_TARGET_REL_TOL,
                "delta_relative_tolerance": CLOSURE_DELTA_REL_TOL,
                "inventory_consistency_relative_tolerance": INVENTORY_CONSISTENCY_REL_TOL,
            },
            "p1": {
                label: case["p1"] for label, case in prepared["cases"].items()
            },
            "pair_contract": prepared["pair"],
            "p2": {"check_input": p2, "constraint_schema": schema},
            "runtime": runtime,
            "decision": decision,
        },
    )
    for marker, evaluation in (("C0", c0), ("C1", c1)):
        print(
            f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_{marker}: "
            + ("PASS" if evaluation["status"] == "PASS" else "HOLD")
        )
        if "average_relative_error" in evaluation:
            print(
                f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_{marker}_TARGET_REL_ERROR: "
                f"{evaluation['average_relative_error']:.12e}"
            )
    delta_pass = decision.get("status") == "PASS"
    print(
        "ISSUE45_INVENTORY_CLOSURE_RUNTIME_DELTA_TRACKING: "
        + ("PASS" if delta_pass else "HOLD")
    )
    if "delta_relative_error" in decision:
        print(
            "ISSUE45_INVENTORY_CLOSURE_RUNTIME_DELTA_REL_ERROR: "
            f"{decision['delta_relative_error']:.12e}"
        )
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_PRECLASS: {decision['status']}")
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_CLASS: {decision['class']}")
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_REASON: {decision['reason']}")
    print(
        f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_C0_LOG: "
        f"{runtime['C0_reference']['log']}"
    )
    print(
        f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_C1_LOG: "
        f"{runtime['C1_shift']['log']}"
    )
    print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_SUMMARY: {summary_path}")
    return 0 if decision["status"] == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Issue45 electron-inventory nullspace/closure validation"
    )
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    parser.add_argument(
        "--macro-electron-average",
        type=float,
        default=DEFAULT_MACRO_ELECTRON_AVG,
        help="macrostate electron average used by --closure-preflight",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--closure-preflight", action="store_true")
    mode.add_argument("--closure-runtime-preflight", action="store_true")
    mode.add_argument("--closure-run", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    try:
        if args.closure_run:
            return run_closure_runtime(qpx=args.qpx, results_root=args.results_root)
        if args.closure_runtime_preflight:
            return run_closure_runtime_preflight(
                qpx=args.qpx, results_root=args.results_root
            )
        if args.closure_preflight:
            return run_closure_preflight(
                qpx=args.qpx,
                results_root=args.results_root,
                macro_avg=args.macro_electron_average,
            )
        return run_preflight(qpx=args.qpx, results_root=args.results_root)
    except (ElectronInventoryNullspaceError, MooseInputError) as exc:
        if args.closure_run or args.closure_runtime_preflight:
            prefix = "ISSUE45_INVENTORY_CLOSURE_RUNTIME"
        elif args.closure_preflight:
            prefix = "ISSUE45_INVENTORY_CLOSURE"
        else:
            prefix = "ISSUE45_INVENTORY_NULLSPACE"
        print(f"{prefix}_PREFLIGHT: HOLD")
        print(f"{prefix}_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(f"{prefix}_REASON: {exc}")
        return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
