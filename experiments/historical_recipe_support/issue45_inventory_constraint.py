"""Issue45 inventory-constraint policy over reusable MOOSE primitives.

The recipe accepts an already-constructed closed electron/Poisson feedback input.
Upstream Issue43 feedback construction remains outside this module.
"""
from __future__ import annotations

import math
from typing import Any

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose.preflight import validate_parser_symbols_text

ISSUE = 45
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
    {"plasma_metal", "plasma_electrode", "plasma_right", "inlet", "outlet"}
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


class Issue45InventoryConstraintError(RuntimeError):
    pass


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


def _ensure_debug_block(text: str) -> str:
    if not mb.has_block(text, "Debug"):
        return mb.append_top_level_block(
            text, "[Debug]\n  show_var_residual_norms = true\n[]"
        )
    return mp.upsert_parameter(text, "Debug", "show_var_residual_norms", "true")


def build_constrained_quasisteady_input(
    feedback_text: str,
    *,
    macro_avg: float,
    runtime_observability: bool = True,
) -> str:
    """Transform a closed feedback input into the Issue45 constrained steady candidate."""
    text = mb.remove_block(feedback_text, "FVKernels/time")
    text = mb.insert_child_block(
        text,
        "Variables",
        f"""  [{LAMBDA_VARIABLE}]
    type = MooseVariableScalar
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{MACRO_AVG_POSTPROCESSOR}]
    type = ConstantPostprocessor
    value = {macro_avg:.17g}
    outputs = none
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVKernels",
        f"""  [r45_inventory_constraint]
    type = {CONSTRAINT_TYPE}
    variable = n_e
    lambda = {LAMBDA_VARIABLE}
    phi0 = {MACRO_AVG_POSTPROCESSOR}
    block = plasma
  []""",
    )
    text = mb.replace_block(
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
    text = mp.upsert_parameter(text, "Outputs/out", "execute_on", "FINAL")
    text = mp.upsert_parameter(text, "Outputs/console", "execute_on", "FINAL")
    if runtime_observability:
        text = _ensure_debug_block(text)
        text = mp.upsert_parameter(text, "Outputs/console", "all_variable_norms", "true")
    return text


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


def evaluate_runtime_case_data(
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
    nonfinite_runtime = bool(diagnostic.get("nonfinite_residuals")) or diagnostic.get("nonlinear_reason") == "DIVERGED_FUNCTION_NANORINF"
    if returncode != 0:
        return {
            "status": "HOLD",
            "class": "SECONDARY_SINGULAR_MODE_SUSPECTED" if zero_pivot else "CONSTRAINED_STEADY_SOLVER_FAIL",
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
    if not all(
        name in final_residuals and math.isfinite(float(final_residuals[name]))
        for name in ("n_e", "potential_plasma")
    ):
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
    consistency_rel_error = abs(avg - inventory / volume) / max(abs(target), 1.0e-300)
    passed = (
        avg_rel_error <= CLOSURE_TARGET_REL_TOL
        and inventory_rel_error <= CLOSURE_TARGET_REL_TOL
        and consistency_rel_error <= INVENTORY_CONSISTENCY_REL_TOL
    )
    return {
        "status": "PASS" if passed else "HOLD",
        "class": "CONSTRAINED_STEADY_CASE_PASS" if passed else "CONSTRAINT_TARGET_TRACKING_FAIL",
        "reason": (
            "constrained steady solution converged and its electron average/inventory track the declared target"
            if passed
            else "constrained steady solution converged but the electron average/inventory does not satisfy the declared target contract"
        ),
        "target": target,
        "target_inventory": target_inventory,
        "target_relative_tolerance": CLOSURE_TARGET_REL_TOL,
        "inventory_consistency_relative_tolerance": INVENTORY_CONSISTENCY_REL_TOL,
        "average_relative_error": avg_rel_error,
        "inventory_relative_error": inventory_rel_error,
        "aggregate_consistency_relative_error": consistency_rel_error,
        "observables": row,
        "final_variable_residuals": final_residuals,
        "diagnostic": diagnostic,
    }


def evaluate_runtime_pair(
    c0: dict[str, Any], c1: dict[str, Any], *, target0: float, target1: float
) -> dict[str, Any]:
    classes = {c0.get("class"), c1.get("class")}
    if "SECONDARY_SINGULAR_MODE_SUSPECTED" in classes:
        return {"status": "HOLD", "class": "SECONDARY_SINGULAR_MODE_SUSPECTED", "reason": "a zero-pivot signature persists after explicit inventory closure"}
    if "CONSTRAINED_STEADY_SOLVER_FAIL" in classes:
        return {"status": "HOLD", "class": "CONSTRAINED_STEADY_SOLVER_FAIL", "reason": "at least one constrained steady target case did not solve"}
    if "CONSTRAINT_TARGET_TRACKING_FAIL" in classes:
        return {"status": "HOLD", "class": "CONSTRAINT_TARGET_TRACKING_FAIL", "reason": "at least one converged target case failed the predeclared inventory tracking contract"}
    if c0.get("status") != "PASS" or c1.get("status") != "PASS":
        return {"status": "HOLD", "class": "CLOSURE_EVIDENCE_INSUFFICIENT", "reason": "at least one target case lacks complete closure evidence"}

    requested_delta = target1 - target0
    if requested_delta == 0.0:
        raise Issue45InventoryConstraintError("runtime target pair must have nonzero separation")
    observed_delta = float(c1["observables"]["n_avg"]) - float(c0["observables"]["n_avg"])
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
        "reason": "both constrained steady target cases converge, satisfy their declared inventory targets, and the observed electron-average shift tracks the requested target shift",
        "requested_delta": requested_delta,
        "observed_delta": observed_delta,
        "delta_relative_error": delta_rel_error,
        "delta_relative_tolerance": CLOSURE_DELTA_REL_TOL,
    }
