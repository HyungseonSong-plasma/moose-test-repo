"""Structural analysis for closed and constrained electron-inventory models."""
from __future__ import annotations
import math
from typing import Any
from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp
from qpx_harness.moose.preflight import validate_parser_symbols_text
from qpx_harness.adapters.moose.electron_inventory.constants import (
    CONSTRAINT_TYPE, DRIFT_TYPE, EXPECTED_CONSTRAINED_ELECTRON_KERNEL_TYPES,
    EXPECTED_DRIFT_BOUNDARIES, EXPECTED_POISSON_GROUNDS,
    EXPECTED_TRANSIENT_ELECTRON_KERNEL_TYPES, LAMBDA_VARIABLE, MACRO_AVG_POSTPROCESSOR,
)
def _truthy(value: str | None) -> bool:
    raw = (mp.unquote(value) or "").lower()
    return raw in {"1", "true", "yes", "on"}


def _electron_kernel_records(text: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in mp.direct_children(text, "FVKernels"):
        if mp.unquote(mp.get_parameter(text, path, "variable")) != "n_e":
            continue
        result.append(
            {"path": path, "type": mp.unquote(mp.get_parameter(text, path, "type"))}
        )
    return result


def _electron_fvbcs(text: str) -> list[dict[str, Any]]:
    if not mb.has_block(text, "FVBCs"):
        return []
    return [
        {"path": path, "type": mp.unquote(mp.get_parameter(text, path, "type"))}
        for path in mp.direct_children(text, "FVBCs")
        if mp.unquote(mp.get_parameter(text, path, "variable")) == "n_e"
    ]


def _poisson_fvbcs(text: str) -> list[dict[str, Any]]:
    if not mb.has_block(text, "FVBCs"):
        return []
    result: list[dict[str, Any]] = []
    for path in mp.direct_children(text, "FVBCs"):
        if mp.unquote(mp.get_parameter(text, path, "variable")) != "potential_plasma":
            continue
        result.append(
            {
                "path": path,
                "boundary": mp.words(mp.get_parameter(text, path, "boundary")),
                "value": mp.unquote(mp.get_parameter(text, path, "value")),
            }
        )
    return result


def _flux_boundary_audit(text: str, electron_kernels: list[dict[str, Any]], add: Any) -> None:
    drift_paths = [x["path"] for x in electron_kernels if x["type"] == DRIFT_TYPE]
    diffusion_paths = [x["path"] for x in electron_kernels if x["type"] == "FVDiffusion"]
    add("one-electrostatic-drift", len(drift_paths) == 1, drift_paths, 1)
    add("one-electron-diffusion", len(diffusion_paths) == 1, diffusion_paths, 1)

    boundaries: set[str] = set()
    forced: list[str] = []
    force_all = False
    if len(drift_paths) == 1:
        drift = drift_paths[0]
        boundaries = set(mp.words(mp.get_parameter(text, drift, "boundaries_to_avoid")))
        forced = mp.words(mp.get_parameter(text, drift, "boundaries_to_force"))
        force_all = _truthy(mp.get_parameter(text, drift, "force_boundary_execution"))
    add(
        "drift-closes-all-plasma-boundaries",
        boundaries == set(EXPECTED_DRIFT_BOUNDARIES),
        sorted(boundaries),
        sorted(EXPECTED_DRIFT_BOUNDARIES),
    )
    add("drift-no-forced-boundaries", not forced, forced, [])
    add("drift-no-force-all-boundaries", not force_all, force_all, False)

    diffusion_forced: list[dict[str, Any]] = []
    for path in diffusion_paths:
        item_forced = mp.words(mp.get_parameter(text, path, "boundaries_to_force"))
        item_force_all = _truthy(mp.get_parameter(text, path, "force_boundary_execution"))
        if item_forced or item_force_all:
            diffusion_forced.append(
                {
                    "path": path,
                    "boundaries_to_force": item_forced,
                    "force_boundary_execution": item_force_all,
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

def _float_parameter(text: str, path: str, name: str) -> float | None:
    raw = mp.unquote(mp.get_parameter(text, path, name))
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
    observed_types = sorted(x["type"] for x in electron_kernels if x["type"])
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
        path
        for path in mp.direct_children(text, "Variables")
        if path.split("/")[-1] == LAMBDA_VARIABLE
    ]
    lambda_type = (
        mp.unquote(mp.get_parameter(text, lambda_paths[0], "type"))
        if len(lambda_paths) == 1
        else None
    )
    add("one-scalar-lagrange-multiplier", len(lambda_paths) == 1, lambda_paths, 1)
    add("scalar-lagrange-multiplier-type", lambda_type == "MooseVariableScalar", lambda_type, "MooseVariableScalar")

    constraint_paths = [
        x["path"] for x in electron_kernels if x["type"] == CONSTRAINT_TYPE
    ]
    add("one-inventory-constraint", len(constraint_paths) == 1, constraint_paths, 1)
    constraint_lambda = None
    constraint_phi0 = None
    constraint_block: list[str] = []
    if len(constraint_paths) == 1:
        path = constraint_paths[0]
        constraint_lambda = mp.unquote(mp.get_parameter(text, path, "lambda"))
        constraint_phi0 = mp.unquote(mp.get_parameter(text, path, "phi0"))
        constraint_block = mp.words(mp.get_parameter(text, path, "block"))
    add("constraint-couples-scalar-lambda", constraint_lambda == LAMBDA_VARIABLE, constraint_lambda, LAMBDA_VARIABLE)
    add("constraint-uses-macro-average-postprocessor", constraint_phi0 == MACRO_AVG_POSTPROCESSOR, constraint_phi0, MACRO_AVG_POSTPROCESSOR)
    add("constraint-block-is-plasma", constraint_block == ["plasma"], constraint_block, ["plasma"])

    pp_paths = [
        path
        for path in mp.direct_children(text, "Postprocessors")
        if path.split("/")[-1] == MACRO_AVG_POSTPROCESSOR
    ]
    pp_type = (
        mp.unquote(mp.get_parameter(text, pp_paths[0], "type"))
        if len(pp_paths) == 1
        else None
    )
    pp_value = _float_parameter(text, pp_paths[0], "value") if len(pp_paths) == 1 else None
    target_tol = max(abs(expected_macro_avg) * 1e-12, 1e-300)
    add("one-macro-average-provider", len(pp_paths) == 1, pp_paths, 1)
    add("macro-average-provider-type", pp_type == "ConstantPostprocessor", pp_type, "ConstantPostprocessor")
    add(
        "macro-average-target-preserved",
        pp_value is not None
        and math.isfinite(pp_value)
        and abs(pp_value - expected_macro_avg) <= target_tol,
        pp_value,
        expected_macro_avg,
    )

    executioner_type = mp.unquote(mp.get_parameter(text, "Executioner", "type"))
    add("steady-executioner", executioner_type == "Steady", executioner_type, "Steady")
    inames = mp.words(mp.get_parameter(text, "Executioner", "petsc_options_iname"))
    values = mp.words(mp.get_parameter(text, "Executioner", "petsc_options_value"))
    add(
        "lm-saddle-factorization-contract",
        "-pc_factor_shift_type" in inames and "NONZERO" in values,
        {"petsc_options_iname": inames, "petsc_options_value": values},
        {"petsc_options_iname": "-pc_factor_shift_type", "petsc_options_value": "NONZERO"},
    )
    add(
        "final-csv-observation",
        mp.words(mp.get_parameter(text, "Outputs/out", "execute_on")) == ["FINAL"],
        mp.words(mp.get_parameter(text, "Outputs/out", "execute_on")),
        ["FINAL"],
    )
    debug = mp.get_parameter(text, "Debug", "show_var_residual_norms") if mb.has_block(text, "Debug") else None
    all_norms = mp.get_parameter(text, "Outputs/console", "all_variable_norms")
    add("runtime-variable-residual-observability", debug == "true", debug, "true")
    add("runtime-console-variable-norms", all_norms == "true", all_norms, "true")

    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": "CONSTRAINED_QUASISTEADY_STRUCTURE_PASS" if not blockers else "CONSERVATION_STRUCTURE_FAIL",
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


def target_only_pair_audit(c0_text: str, c1_text: str) -> dict[str, Any]:
    path = f"Postprocessors/{MACRO_AVG_POSTPROCESSOR}"
    c0_normalized = mp.upsert_parameter(c0_text, path, "value", "<TARGET>")
    c1_normalized = mp.upsert_parameter(c1_text, path, "value", "<TARGET>")
    equal = c0_normalized == c1_normalized
    return {
        "status": "PASS" if equal else "HOLD",
        "class": "TARGET_ONLY_PAIR_PASS" if equal else "PAIR_CONSTRUCTION_MISMATCH",
        "reason": (
            "C0/C1 inputs are byte-identical after normalizing the declared macro electron-average target"
            if equal
            else "C0/C1 differ in construction beyond the declared macro electron-average target"
        ),
    }

def audit_closed_electron_structure(text: str) -> dict[str, Any]:
    """Audit prerequisites for the accepted closed/source-free nullspace identity."""
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
        "left_null_vector": "[1^T, 0]" if not blockers else None,
        "derivation_scope": (
            "steady spatial n_e residual only; transient FVTimeKernel excluded "
            "from the nullspace identity"
        ),
    }

