"""Semantic runtime owner for the Issue46 augmented Jacobian-localization audit.

Construction is owned by ``recipes.issue46_jacobian_localization``. Generic
DOF ownership, PETSc matrix facts, and PETSc option manipulation are delegated
to reusable primitives. This module owns only the Issue46-specific structural
policy, framework-control contract, localization classification, evidence, and
P0/P1/P2/P3 orchestration. It intentionally does not depend on the historical
``augmented_jacobian_localization`` owner.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from recipes import issue45_first_linear as first_linear_policy
from recipes import issue46_jacobian_localization as localization_recipe

from . import artifacts
from . import electron_inventory_nullspace as inv
from . import evidence
from . import issue43_coupling_diagnostic as coupling_diag
from .moose import blocks as mb
from .moose import dofmap as dm
from .moose import parameters as mp
from .moose_input import MooseInput, MooseInputError
from .petsc import matrix as pm
from .petsc import options as po
from .runtime import resolve_executable, run_qpx, validate_executable

ISSUE = 46
TARGET = localization_recipe.TARGET
LOCALIZATION_THRESHOLD = localization_recipe.LOCALIZATION_THRESHOLD
DOFMAP_OUTPUT = localization_recipe.DOFMAP_OUTPUT
DOFMAP_FILE_BASE = localization_recipe.DOFMAP_FILE_BASE
GLOBAL_JACOBIAN_REL_TOL = first_linear_policy.JACOBIAN_REL_TOL
FRAMEWORK_CONTROL_REL_TOL = 5.0e-8
DOMINANT_ENERGY_FRACTION = 0.80
MAIN_VARIABLES = ("n_e", "potential_plasma", inv.LAMBDA_VARIABLE)
SCALAR_VARIABLES = (inv.LAMBDA_VARIABLE,)
CONCLUSIVE_LOCALIZATION_CLASSES = {
    "CONSTRAINT_LM_BLOCK_MISMATCH",
    "ELECTRON_POTENTIAL_BLOCK_MISMATCH",
    "OTHER_BLOCK_MISMATCH",
}


class Issue46JacobianLocalizationError(RuntimeError):
    pass


AugmentedJacobianLocalizationError = Issue46JacobianLocalizationError
instrument_localization = localization_recipe.instrument_localization


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    artifacts.write_json_bundle(path.parent, {"summary": (path.name, payload)})


def _normalized_localization_text(text: str) -> str:
    out = text
    output_path = f"Outputs/{DOFMAP_OUTPUT}"
    if mb.has_block(out, output_path):
        out = mb.remove_block(out, output_path)
    out = mp.upsert_parameter(out, "Executioner", "petsc_options", "'<PETSC_FLAGS>'")
    out = mp.upsert_parameter(out, "Executioner", "petsc_options_iname", "'<PETSC_INAMES>'")
    return mp.upsert_parameter(out, "Executioner", "petsc_options_value", "'<PETSC_VALUES>'")


def audit_localization_structure(base_first_linear: str, localization_text: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, observed: Any, required: Any) -> None:
        checks.append({"id": name, "status": "PASS" if ok else "FAIL", "observed": observed, "required": required})

    closure = inv.audit_constrained_quasisteady_structure(localization_text, expected_macro_avg=TARGET)
    add("canonical-c0-closure-structure", closure["status"] == "PASS", closure["status"], "PASS")
    nl_max = mp.unquote(mp.get_parameter(localization_text, "Executioner", "nl_max_its"))
    add("first-linear-horizon-preserved", nl_max == "1", nl_max, "1")

    expected_flags = [flag for flag in po.get_flags(base_first_linear) if flag != "-snes_test_jacobian"]
    if "-snes_test_jacobian_view" not in expected_flags:
        expected_flags.append("-snes_test_jacobian_view")
    actual_flags = po.get_flags(localization_text)
    add("localization-petsc-flags-exact", actual_flags == expected_flags, actual_flags, expected_flags)

    base_pairs = po.get_name_value_pairs(base_first_linear)
    expected_pairs = list(base_pairs) + [("-snes_test_jacobian", f"{LOCALIZATION_THRESHOLD:.12g}")]
    actual_pairs = po.get_name_value_pairs(localization_text)
    add("localization-threshold-pair-exact", actual_pairs == expected_pairs, actual_pairs, expected_pairs)

    output_path = f"Outputs/{DOFMAP_OUTPUT}"
    outputs = mp.direct_children(localization_text, "Outputs")
    add("one-localization-dofmap-output", outputs.count(output_path) == 1, outputs, output_path)
    if output_path in outputs:
        dof_type = mp.unquote(mp.get_parameter(localization_text, output_path, "type"))
        dof_execute = mp.words(mp.get_parameter(localization_text, output_path, "execute_on"))
        dof_base = mp.unquote(mp.get_parameter(localization_text, output_path, "file_base"))
    else:
        dof_type, dof_execute, dof_base = None, [], None
    add("dofmap-type", dof_type == "DOFMap", dof_type, "DOFMap")
    add("dofmap-initial-only", dof_execute == ["INITIAL"], dof_execute, ["INITIAL"])
    add("dofmap-file-base", dof_base == DOFMAP_FILE_BASE, dof_base, DOFMAP_FILE_BASE)

    same = _normalized_localization_text(base_first_linear) == _normalized_localization_text(localization_text)
    add("observability-only-input-difference", same, same, True)
    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": "JACOBIAN_LOCALIZATION_STRUCTURE_PASS" if not blockers else "JACOBIAN_LOCALIZATION_STRUCTURE_FAIL",
        "checks": checks,
        "blockers": blockers,
        "closure": closure,
    }


def build_framework_control_input() -> str:
    return """[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 21
  xmax = 2
[]

[Variables]
  [v]
    type = MooseVariableFVReal
    two_term_boundary_expansion = false
  []
  [lambda]
    family = SCALAR
    order = FIRST
  []
[]

[FVKernels]
  [diffusion]
    type = FVDiffusion
    variable = v
    coeff = 1
  []
  [lambda_constraint]
    type = FVIntegralValueConstraint
    variable = v
    lambda = lambda
    phi0 = 1
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  nl_rel_tol = 1e-12
  petsc_options = '-snes_test_jacobian -snes_converged_reason'
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]

[Outputs]
  console = true
[]
"""


def audit_framework_control_structure(text: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, observed: Any, required: Any) -> None:
        checks.append({"id": name, "status": "PASS" if ok else "FAIL", "observed": observed, "required": required})

    MooseInput(text)
    get = lambda path, name: mp.unquote(mp.get_parameter(text, path, name))
    add("mesh-type", get("Mesh", "type") == "GeneratedMesh", get("Mesh", "type"), "GeneratedMesh")
    add("mesh-dim", get("Mesh", "dim") == "1", get("Mesh", "dim"), "1")
    add("fv-variable", get("Variables/v", "type") == "MooseVariableFVReal", get("Variables/v", "type"), "MooseVariableFVReal")
    add("fv-boundary-expansion", get("Variables/v", "two_term_boundary_expansion") == "false", get("Variables/v", "two_term_boundary_expansion"), "false")
    add("scalar-family", get("Variables/lambda", "family") == "SCALAR", get("Variables/lambda", "family"), "SCALAR")
    add("scalar-order", get("Variables/lambda", "order") == "FIRST", get("Variables/lambda", "order"), "FIRST")

    kernel_paths = mp.direct_children(text, "FVKernels")
    expected_kernels = {"FVKernels/diffusion", "FVKernels/lambda_constraint"}
    add("control-kernel-set", set(kernel_paths) == expected_kernels, kernel_paths, sorted(expected_kernels))
    diffusion_type = get("FVKernels/diffusion", "type") if "FVKernels/diffusion" in kernel_paths else None
    diffusion_variable = get("FVKernels/diffusion", "variable") if "FVKernels/diffusion" in kernel_paths else None
    diffusion_coeff = get("FVKernels/diffusion", "coeff") if "FVKernels/diffusion" in kernel_paths else None
    add("control-diffusion-type", diffusion_type == "FVDiffusion", diffusion_type, "FVDiffusion")
    add("control-diffusion-variable", diffusion_variable == "v", diffusion_variable, "v")
    add("control-diffusion-coeff", diffusion_coeff == "1", diffusion_coeff, "1")
    all_kernel_types = [get(path, "type") for path in kernel_paths]
    add("no-moose-testapp-fvelementaladvection", "FVElementalAdvection" not in all_kernel_types, all_kernel_types, "FVElementalAdvection absent")

    add("control-constraint-type", get("FVKernels/lambda_constraint", "type") == "FVIntegralValueConstraint", get("FVKernels/lambda_constraint", "type"), "FVIntegralValueConstraint")
    add("control-constraint-variable", get("FVKernels/lambda_constraint", "variable") == "v", get("FVKernels/lambda_constraint", "variable"), "v")
    add("control-constraint-lambda", get("FVKernels/lambda_constraint", "lambda") == "lambda", get("FVKernels/lambda_constraint", "lambda"), "lambda")
    add("control-constraint-phi0", get("FVKernels/lambda_constraint", "phi0") == "1", get("FVKernels/lambda_constraint", "phi0"), "1")
    add("control-steady", get("Executioner", "type") == "Steady", get("Executioner", "type"), "Steady")
    add("control-newton", get("Executioner", "solve_type") == "NEWTON", get("Executioner", "solve_type"), "NEWTON")
    add("control-auto-scaling", get("Executioner", "automatic_scaling") == "true", get("Executioner", "automatic_scaling"), "true")
    add("control-offdiag-scaling", get("Executioner", "off_diagonals_in_auto_scaling") == "true", get("Executioner", "off_diagonals_in_auto_scaling"), "true")
    flags = po.get_flags(text)
    add("control-jacobian-observability", "-snes_test_jacobian" in flags, flags, "-snes_test_jacobian")
    pairs = po.get_name_value_pairs(text)
    expected_pairs = [("-pc_type", "lu"), ("-pc_factor_shift_type", "NONZERO")]
    add("control-lu-nonzero", pairs == expected_pairs, pairs, expected_pairs)

    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": "MOOSE_CONSTRAINT_CONTROL_STRUCTURE_PASS" if not blockers else "MOOSE_CONSTRAINT_CONTROL_FAIL",
        "checks": checks,
        "blockers": blockers,
        "source_contract": {
            "reference_source": {"project": "MOOSE", "revision": "9f388366ccf", "purpose": "framework-control source contract"},
            "runtime_identity": "OBSERVED_SEPARATELY",
            "control_operator": "FVDiffusion",
            "control_operator_registration": "MooseApp",
            "rejected_test_only_operator": "FVElementalAdvection",
            "official_constraint_regression_ratio_tol": FRAMEWORK_CONTROL_REL_TOL,
            "runtime_jacobian_execution_deferred_to_p3": True,
        },
    }


def parse_dof_map_text(text: str, *, expected_variables: tuple[str, ...] = MAIN_VARIABLES, scalar_variables: tuple[str, ...] = SCALAR_VARIABLES) -> dict[str, Any]:
    try:
        return dm.parse_dof_map_text(text, expected_variables=expected_variables, scalar_variables=scalar_variables)
    except dm.DofMapError as exc:
        raise Issue46JacobianLocalizationError(str(exc)) from exc


def parse_threshold_difference_matrix(text: str) -> dict[str, Any]:
    try:
        return pm.parse_threshold_difference_matrix(text)
    except pm.MatrixParseError as exc:
        raise Issue46JacobianLocalizationError(str(exc)) from exc


def _category(row_var: str, col_var: str) -> str:
    lm = inv.LAMBDA_VARIABLE
    if row_var == lm or col_var == lm:
        return "constraint_lm"
    if {row_var, col_var} == {"n_e", "potential_plasma"}:
        return "electron_potential"
    return "other"


def localize_difference_entries(difference: dict[str, Any], dof_map: dict[str, Any]) -> dict[str, Any]:
    try:
        facts = pm.summarize_by_owner(difference, dof_map["owner_by_dof"])
    except (KeyError, pm.MatrixParseError) as exc:
        raise Issue46JacobianLocalizationError(str(exc)) from exc

    category_energy = {"constraint_lm": 0.0, "electron_potential": 0.0, "other": 0.0}
    for block in facts["blocks"].values():
        category = _category(block["row_variable"], block["col_variable"])
        category_energy[category] += float(block["sum_squared_difference"])
    total_energy = sum(category_energy.values())
    fractions = {name: (energy / total_energy if total_energy > 0.0 else 0.0) for name, energy in category_energy.items()}
    return {**facts, "category_energy_fraction": fractions}


def analyze_localization_text(log_text: str, dofmap_text: str, *, framework_control_pass: bool = True) -> dict[str, Any]:
    if not framework_control_pass:
        return {"status": "HOLD", "class": "MOOSE_CONSTRAINT_CONTROL_FAIL", "reason": "the same-runtime known-good FVIntegralValueConstraint control failed its Jacobian contract"}

    jacobian = coupling_diag.analyze_jacobian_text(log_text, relative_tolerance=GLOBAL_JACOBIAN_REL_TOL)
    if jacobian.get("class") != "JACOBIAN_MISMATCH":
        return {"status": "HOLD", "class": "JACOBIAN_LOCALIZATION_INSUFFICIENT", "reason": "the historical augmented Jacobian mismatch was not reproduced in the localization log", "jacobian": jacobian}

    try:
        dof_map = parse_dof_map_text(dofmap_text)
        difference = parse_threshold_difference_matrix(log_text)
        localized = localize_difference_entries(difference, dof_map)
    except Issue46JacobianLocalizationError as exc:
        return {"status": "HOLD", "class": "JACOBIAN_LOCALIZATION_INSUFFICIENT", "reason": str(exc), "jacobian": jacobian}

    result: dict[str, Any] = {
        "status": "PASS",
        "jacobian": jacobian,
        "dof_map": {"ndof": dof_map["ndof"], "variables": dof_map["variables"]},
        "difference": difference,
        "localization": localized,
        "dominant_energy_fraction_required": DOMINANT_ENERGY_FRACTION,
    }
    if localized["unmapped_entries"]:
        result.update({"status": "HOLD", "class": "JACOBIAN_LOCALIZATION_INSUFFICIENT", "reason": "one or more thresholded Jacobian-difference entries could not be mapped to nonlinear variables"})
        return result
    if localized["mapped_entry_count"] == 0:
        result.update({"status": "HOLD", "class": "FD_SCALING_LIMIT_SUSPECTED", "reason": "global Frobenius mismatch persists but no individual difference exceeds the predeclared localization threshold; a separate FD/scaling verification is required"})
        return result

    fractions = localized["category_energy_fraction"]
    if fractions["constraint_lm"] >= DOMINANT_ENERGY_FRACTION:
        klass = "CONSTRAINT_LM_BLOCK_MISMATCH"
        reason = "thresholded Jacobian-difference energy is dominated by blocks involving the inventory Lagrange multiplier"
    elif fractions["electron_potential"] >= DOMINANT_ENERGY_FRACTION:
        klass = "ELECTRON_POTENTIAL_BLOCK_MISMATCH"
        reason = "thresholded Jacobian-difference energy is dominated by n_e <-> potential_plasma cross-coupling blocks"
    else:
        klass = "OTHER_BLOCK_MISMATCH"
        reason = "thresholded Jacobian-difference energy is not dominated by the declared LM or electron-potential cross-coupling classes"
    result.update({"class": klass, "reason": reason})
    return result


def analyze_framework_control_runtime(log_text: str, *, returncode: int) -> dict[str, Any]:
    jacobian = coupling_diag.analyze_jacobian_text(log_text, relative_tolerance=FRAMEWORK_CONTROL_REL_TOL)
    passed = jacobian.get("class") == "JACOBIAN_CORRECTNESS_PASS"
    return {
        "status": "PASS" if passed else "HOLD",
        "class": "FRAMEWORK_CONTROL_JACOBIAN_PASS" if passed else "MOOSE_CONSTRAINT_CONTROL_FAIL",
        "reason": f"same-runtime production-framework constraint control satisfies the predeclared Jacobian ratio tolerance {FRAMEWORK_CONTROL_REL_TOL:g}" if passed else f"same-runtime production-framework constraint control does not satisfy the predeclared Jacobian ratio tolerance {FRAMEWORK_CONTROL_REL_TOL:g}",
        "returncode": returncode,
        "jacobian": jacobian,
    }


def evaluate_runtime_batch(control: dict[str, Any], localization: dict[str, Any] | None) -> dict[str, Any]:
    if control.get("status") != "PASS":
        return {"status": "HOLD", "class": "MOOSE_CONSTRAINT_CONTROL_FAIL", "reason": control.get("reason", "framework-control Jacobian failed")}
    if not localization:
        return {"status": "HOLD", "class": "JACOBIAN_LOCALIZATION_INSUFFICIENT", "reason": "framework control passed but the C0 localization member is missing"}
    klass = localization.get("class")
    if localization.get("status") == "PASS" and klass in CONCLUSIVE_LOCALIZATION_CLASSES:
        return {"status": "PASS", "class": klass, "reason": localization.get("reason", "C0 mismatch localized")}
    return {"status": "HOLD", "class": klass or "JACOBIAN_LOCALIZATION_INSUFFICIENT", "reason": localization.get("reason", "C0 entry-wise localization is insufficient")}


def build_jacobian_localization_stats(
    *,
    runtime: dict[str, Any],
    analysis: dict[str, Any],
) -> Any:
    """Map existing Issue46 runtime/localization facts into canonical Stats."""

    from .analysis.stats_builder import (
        build_accuracy_stats,
        build_runtime_simulation_stats,
    )

    jacobian = analysis.get("jacobian")
    difference = analysis.get("difference")
    localization = analysis.get("localization")

    matrix_comparisons: tuple[dict[str, Any], ...] = ()
    if isinstance(difference, dict):
        finite = pm.finite_nonzero_entries(difference)
        matrix_comparison: dict[str, Any] = {
            "name": "thresholded_jacobian_difference",
            **finite,
        }
        if isinstance(localization, dict):
            matrix_comparison.update(
                {
                    "mapped_entry_count": localization.get("mapped_entry_count"),
                    "thresholded_l2_difference": localization.get(
                        "thresholded_l2_difference"
                    ),
                    "blocks": localization.get("blocks"),
                }
            )
        matrix_comparisons = (matrix_comparison,)

    accuracy = build_accuracy_stats(
        jacobian_comparisons=(
            jacobian.get("tests", ()) if isinstance(jacobian, dict) else ()
        ),
        matrix_comparisons=matrix_comparisons,
    )
    return build_runtime_simulation_stats(runtime, accuracy=accuracy)


def _synthetic_dof_map() -> str:
    return json.dumps({"ndof": 5, "demangled": True, "vars": [{"name": "n_e", "subdomains": [{"id": 1, "kernels": [], "dofs": [0, 1]}]}, {"name": "potential_plasma", "subdomains": [{"id": 1, "kernels": [], "dofs": [2, 3]}]}, {"name": inv.LAMBDA_VARIABLE, "subdomains": [{"id": 1, "kernels": [], "dofs": []}]}]})


def _synthetic_jacobian_log(relative_error: float) -> str:
    return "  ---------- Testing Jacobian -------------\n" + f"  ||J - Jfd||_F/||J||_F = {relative_error:.12e}, ||J - Jfd||_F = 1.0e-10\n"


def _synthetic_localization_log(entries: list[tuple[int, int, float]], jac_rel: float = 4.0e-5) -> str:
    rows: dict[int, list[tuple[int, float]]] = {}
    for row, col, value in entries:
        rows.setdefault(row, []).append((col, value))
    matrix_lines = []
    for row in sorted(rows):
        payload = " ".join(f"({col}, {value:.12e})" for col, value in rows[row])
        matrix_lines.append(f"row {row}: {payload}")
    return (
        "  ---------- Testing Jacobian -------------\n"
        f"  ||J - Jfd||_F/||J||_F = {jac_rel:.12e}, ||J - Jfd||_F = 8.0e-04\n"
        f"  Hand-coded minus finite-difference Jacobian with tolerance {LOCALIZATION_THRESHOLD:.12e} ----------\n"
        "Mat Object: 1 MPI process\n  type: seqaij\n"
        + "\n".join(matrix_lines)
        + "\nLinear solve did not converge due to DIVERGED_BREAKDOWN iterations 30\n"
    )


def self_test() -> int:
    try:
        base = inv._synthetic_constrained_input(TARGET)
        first_text, _ = first_linear_policy.instrument_first_linear(base)
        localized_text, _ = instrument_localization(first_text)
        if audit_localization_structure(first_text, localized_text)["status"] != "PASS":
            raise AssertionError("positive localization structure did not pass")
        mutated = localized_text.replace("file_base = r46_dofmap", "file_base = wrong_dofmap", 1)
        if audit_localization_structure(first_text, mutated)["status"] == "PASS":
            raise AssertionError("DOFMap output mutation was accepted")

        control_text = build_framework_control_input()
        if audit_framework_control_structure(control_text)["status"] != "PASS":
            raise AssertionError("known-good framework control structure did not pass")
        bad_control = control_text.replace("off_diagonals_in_auto_scaling = true", "off_diagonals_in_auto_scaling = false", 1)
        if audit_framework_control_structure(bad_control)["status"] == "PASS":
            raise AssertionError("framework-control scaling mutation was accepted")
        test_only_control = control_text.replace("type = FVDiffusion", "type = FVElementalAdvection", 1)
        if audit_framework_control_structure(test_only_control)["status"] == "PASS":
            raise AssertionError("MooseTestApp-only FVElementalAdvection mutation was accepted")
        wrong_coeff = control_text.replace("coeff = 1", "coeff = 2", 1)
        if audit_framework_control_structure(wrong_coeff)["status"] == "PASS":
            raise AssertionError("framework-control diffusion coefficient mutation was accepted")

        dofmap = _synthetic_dof_map()
        parsed = parse_dof_map_text(dofmap)
        if parsed["owner_by_dof"].get(4) != inv.LAMBDA_VARIABLE:
            raise AssertionError("scalar fallback DOF mapping failed")

        lm_log = _synthetic_localization_log([(0, 4, 2.0e-4), (4, 1, -3.0e-4)])
        lm_result = analyze_localization_text(lm_log, dofmap)
        if lm_result["class"] != "CONSTRAINT_LM_BLOCK_MISMATCH":
            raise AssertionError("LM block mismatch did not classify")

        stats = build_jacobian_localization_stats(
            runtime={"case_id": "C0_LOCALIZATION", "returncode": 1, "wall_seconds": 0.5},
            analysis=lm_result,
        )
        if (
            stats.common.case_id != "C0_LOCALIZATION"
            or stats.common.return_code != 1
            or stats.common.wall_time_seconds != 0.5
            or stats.accuracy is None
        ):
            raise AssertionError("Issue46 Stats common/accuracy mapping drifted")
        jacobian_error = next(
            item for item in stats.accuracy.matrix_errors if item.name == "jacobian_fd"
        )
        localized_error = next(
            item
            for item in stats.accuracy.matrix_errors
            if item.name == "thresholded_jacobian_difference"
        )
        if (
            jacobian_error.error.relative_error != 4.0e-5
            or jacobian_error.error.absolute_error != 8.0e-4
            or localized_error.threshold != LOCALIZATION_THRESHOLD
            or localized_error.structural_entry_count != 2
            or localized_error.nonzero_thresholded_entry_count != 2
            or localized_error.mapped_entry_count != 2
            or not math.isclose(
                float(localized_error.thresholded_l2_difference),
                math.sqrt((2.0e-4) ** 2 + (3.0e-4) ** 2),
                rel_tol=1.0e-12,
            )
            or len(localized_error.blocks) != 2
            or len(localized_error.entries) != 2
        ):
            raise AssertionError("Issue46 matrix/Jacobian Stats mapping drifted")
        if stats.convergence is not None:
            raise AssertionError("unproduced convergence facts were invented")
        if hasattr(stats, "decision") or hasattr(stats, "evidence"):
            raise AssertionError("policy/evidence leaked into Stats")
        print("ISSUE46_JAC_LOCALIZATION_STATS_MAPPING_SELFTEST: PASS")

        ep_log = _synthetic_localization_log([(0, 2, 2.0e-4), (3, 1, -3.0e-4)])
        if analyze_localization_text(ep_log, dofmap)["class"] != "ELECTRON_POTENTIAL_BLOCK_MISMATCH":
            raise AssertionError("electron-potential block mismatch did not classify")
        other_log = _synthetic_localization_log([(0, 1, 2.0e-4), (2, 3, -3.0e-4)])
        if analyze_localization_text(other_log, dofmap)["class"] != "OTHER_BLOCK_MISMATCH":
            raise AssertionError("other block mismatch did not classify")
        empty_log = _synthetic_localization_log([])
        if analyze_localization_text(empty_log, dofmap)["class"] != "FD_SCALING_LIMIT_SUSPECTED":
            raise AssertionError("empty thresholded difference did not route to FD/scaling suspicion")

        control_pass = analyze_framework_control_runtime(_synthetic_jacobian_log(1.0e-9), returncode=0)
        if control_pass["status"] != "PASS":
            raise AssertionError("framework-control positive runtime did not pass")
        control_fail = analyze_framework_control_runtime(_synthetic_jacobian_log(1.0e-6), returncode=0)
        if control_fail["class"] != "MOOSE_CONSTRAINT_CONTROL_FAIL":
            raise AssertionError("framework-control Jacobian mutation was accepted")
        if evaluate_runtime_batch(control_fail, lm_result)["class"] != "MOOSE_CONSTRAINT_CONTROL_FAIL":
            raise AssertionError("framework-control failure did not take precedence")
        batch = evaluate_runtime_batch(control_pass, lm_result)
        if batch["status"] != "PASS" or batch["class"] != "CONSTRAINT_LM_BLOCK_MISMATCH":
            raise AssertionError("conclusive localization batch did not pass")

        missing_view = lm_log.split("Hand-coded minus finite-difference", 1)[0]
        if analyze_localization_text(missing_view, dofmap)["class"] != "JACOBIAN_LOCALIZATION_INSUFFICIENT":
            raise AssertionError("missing matrix view was over-classified")
    except Exception as exc:
        print(f"ISSUE46_JAC_LOCALIZATION_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE46_JAC_LOCALIZATION_SELFTEST: PASS")
    print("ISSUE46_JAC_LOCALIZATION_RUNTIME_SELFTEST: PASS")
    return 0


def _prepare_cases(exe: Path, results_root: str | None) -> dict[str, Any]:
    base_case, base_text, radial_span = inv._base_case_context()
    base_c0 = inv._build_constrained_quasisteady_input(base_text, radial_span=radial_span, macro_avg=TARGET, runtime_observability=True)
    first_text, _ = first_linear_policy.instrument_first_linear(base_c0)
    localization_text, instrumentation = instrument_localization(first_text)
    p1_main = audit_localization_structure(first_text, localization_text)

    control_text = build_framework_control_input()
    p1_control = audit_framework_control_structure(control_text)

    root = inv._evidence_root(exe=exe, results_root=results_root, stem="issue46_augmented_jacobian_localization")
    main_dir = root / "c0_localization"
    control_dir = root / "framework_control"
    inv._stage_case(base_case, main_dir, localization_text)
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "input.i").write_text(control_text)
    return {"root": root, "main_dir": main_dir, "main_input": main_dir / "input.i", "control_dir": control_dir, "control_input": control_dir / "input.i", "p1_main": p1_main, "p1_control": p1_control, "instrumentation": instrumentation}


def _check_input(exe: Path, case_dir: Path, log_path: Path) -> dict[str, Any]:
    run = run_qpx(exe, cwd=case_dir, input_name="input.i", log_path=log_path, extra_args=("--check-input", "--color", "off"), stream=False)
    return {"status": "PASS" if run.returncode == 0 else "HOLD", "returncode": run.returncode, "wall_seconds": run.wall_seconds, "log": str(log_path), "identity": {**evidence.identity_record(executable=exe, input_path=case_dir / "input.i"), "qpx_sha256": evidence.sha256_file(exe)}}


def _preflight_reports(exe: Path, prepared: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    p1_main = prepared["p1_main"]["status"] == "PASS"
    p1_control = prepared["p1_control"]["status"] == "PASS"
    p2_main = _check_input(exe, prepared["main_dir"], prepared["root"] / "p2_c0_check_input.log") if p1_main else {}
    p2_control = _check_input(exe, prepared["control_dir"], prepared["root"] / "p2_control_check_input.log") if p1_control else {}
    status = "PASS" if p1_main and p1_control and p2_main.get("status") == "PASS" and p2_control.get("status") == "PASS" else "HOLD"
    return p2_main, p2_control, status


def _preflight_payload(prepared: dict[str, Any], p2_main: dict[str, Any], p2_control: dict[str, Any], status: str) -> dict[str, Any]:
    if prepared["p1_control"]["status"] != "PASS" or p2_control.get("status") != "PASS":
        decision_class = "HARNESS_OR_CONSTRUCTION_FAIL"
        reason = "the production-registered framework control did not pass construction/check-input preflight"
    elif status == "PASS":
        decision_class = "JACOBIAN_LOCALIZATION_RUNTIME_BATCH_READY"
        reason = "the exact C0 localization case and production-registered same-runtime framework control pass P0/P1/P2; the bounded runtime batch is implemented but has not been executed"
    else:
        decision_class = "HARNESS_OR_CONSTRUCTION_FAIL"
        reason = "the Issue46 localization harness did not pass all P0/P1/P2 gates"
    return {
        "issue": ISSUE,
        "mode": "augmented-jacobian-localization-preflight",
        "status": status,
        "p3_executed": False,
        "p3_authorized_by_harness": False,
        "evr_consumed_by_preflight": False,
        "target": TARGET,
        "localization_threshold": LOCALIZATION_THRESHOLD,
        "global_jacobian_rel_tol": GLOBAL_JACOBIAN_REL_TOL,
        "framework_control_rel_tol": FRAMEWORK_CONTROL_REL_TOL,
        "framework_control_operator": "FVDiffusion",
        "framework_control_operator_registration": "MooseApp",
        "runtime_batch_implemented": True,
        "runtime_batch_members": ["framework-control Jacobian", "exact C0 entry-wise localization"],
        "runtime_batch_fail_fast_on_control_failure": True,
        "instrumentation": prepared["instrumentation"],
        "p1": {"c0_localization": prepared["p1_main"], "framework_control": prepared["p1_control"]},
        "p2": {"c0_check_input": p2_main, "framework_control_check_input": p2_control},
        "framework_control_runtime": {"executed": False, "reason": "runtime Jacobian control is reserved for the same explicitly authorized P3 batch as C0 localization"},
        "decision": {"status": status, "class": decision_class, "reason": reason},
    }


def run_preflight(qpx: str | None, results_root: str | None) -> int:
    exe = resolve_executable(qpx)
    validate_executable(exe)
    prepared = _prepare_cases(exe, results_root)
    p2_main, p2_control, status = _preflight_reports(exe, prepared)
    path = prepared["root"] / "summary.json"
    _write_json(path, _preflight_payload(prepared, p2_main, p2_control, status))

    print(f"ISSUE46_JAC_LOCALIZATION_P1_C0: {prepared['p1_main']['status']}")
    print(f"ISSUE46_JAC_LOCALIZATION_P1_CONTROL: {prepared['p1_control']['status']}")
    print(f"ISSUE46_JAC_LOCALIZATION_P2_C0_CHECK_INPUT: {p2_main.get('status', 'HOLD')}")
    print(f"ISSUE46_JAC_LOCALIZATION_P2_CONTROL_CHECK_INPUT: {p2_control.get('status', 'HOLD')}")
    print("ISSUE46_JAC_LOCALIZATION_P2_CONTROL_RUNTIME: DEFERRED_TO_AUTHORIZED_P3")
    print(f"ISSUE46_JAC_LOCALIZATION_PREFLIGHT: {status}")
    print("ISSUE46_JAC_LOCALIZATION_CLASS: " + ("JACOBIAN_LOCALIZATION_RUNTIME_BATCH_READY" if status == "PASS" else "HARNESS_OR_CONSTRUCTION_FAIL"))
    print(f"ISSUE46_JAC_LOCALIZATION_SUMMARY: {path}")
    return 0 if status == "PASS" else 2


def _purge_dofmap_outputs(case_dir: Path) -> None:
    for path in case_dir.glob(f"{DOFMAP_FILE_BASE}*.json"):
        if path.is_file():
            path.unlink()


def _run_runtime_case(exe: Path, *, case_id: str, case_dir: Path, log_path: Path) -> dict[str, Any]:
    print(f"ISSUE46_JAC_LOCALIZATION_CASE_START: {case_id}")
    run = run_qpx(exe, cwd=case_dir, input_name="input.i", log_path=log_path, extra_args=("--color", "off"), stream=False)
    print(f"ISSUE46_JAC_LOCALIZATION_CASE_END: {case_id} rc={run.returncode}")
    return {"case_id": case_id, "returncode": run.returncode, "wall_seconds": run.wall_seconds, "log": str(log_path), "identity": {**evidence.identity_record(executable=exe, input_path=case_dir / "input.i"), "qpx_sha256": evidence.sha256_file(exe)}}


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def run_runtime(qpx: str | None, results_root: str | None) -> int:
    exe = resolve_executable(qpx)
    validate_executable(exe)
    prepared = _prepare_cases(exe, results_root)
    p2_main, p2_control, preflight_status = _preflight_reports(exe, prepared)

    if preflight_status != "PASS":
        payload = _preflight_payload(prepared, p2_main, p2_control, preflight_status)
        payload["mode"] = "augmented-jacobian-localization-runtime-gated"
        payload["decision"] = {"status": "HOLD", "class": "HARNESS_OR_CONSTRUCTION_FAIL", "reason": "runtime entry refused because P0/P1/P2 preflight is not PASS"}
        path = prepared["root"] / "summary.json"
        _write_json(path, payload)
        print("ISSUE46_JAC_LOCALIZATION_PRECLASS: HOLD")
        print("ISSUE46_JAC_LOCALIZATION_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print("ISSUE46_JAC_LOCALIZATION_REASON: runtime entry refused because P0/P1/P2 preflight is not PASS")
        print(f"ISSUE46_JAC_LOCALIZATION_SUMMARY: {path}")
        return 2

    control_log = prepared["root"] / "p3_framework_control.log"
    control_run = _run_runtime_case(exe, case_id="FRAMEWORK_CONTROL", case_dir=prepared["control_dir"], log_path=control_log)
    control_analysis = analyze_framework_control_runtime(control_log.read_text(errors="replace"), returncode=control_run["returncode"])
    control_worst = _finite_or_none(control_analysis.get("jacobian", {}).get("worst_relative_frobenius_error"))
    print(f"ISSUE46_JAC_LOCALIZATION_CONTROL_JACOBIAN: {control_analysis['status']}")
    if control_worst is not None:
        print(f"ISSUE46_JAC_LOCALIZATION_CONTROL_JACOBIAN_REL_ERROR: {control_worst:.12e}")

    c0_run: dict[str, Any] | None = None
    c0_analysis: dict[str, Any] | None = None
    dofmap_path = prepared["main_dir"] / f"{DOFMAP_FILE_BASE}.json"
    if control_analysis["status"] == "PASS":
        _purge_dofmap_outputs(prepared["main_dir"])
        c0_log = prepared["root"] / "p3_c0_localization.log"
        c0_run = _run_runtime_case(exe, case_id="C0_LOCALIZATION", case_dir=prepared["main_dir"], log_path=c0_log)
        if not dofmap_path.is_file():
            c0_analysis = {"status": "HOLD", "class": "JACOBIAN_LOCALIZATION_INSUFFICIENT", "reason": f"expected DOFMap output is missing: {dofmap_path}"}
        else:
            c0_analysis = analyze_localization_text(c0_log.read_text(errors="replace"), dofmap_path.read_text(errors="replace"), framework_control_pass=True)
    else:
        print("ISSUE46_JAC_LOCALIZATION_C0_RUNTIME: SKIPPED_CONTROL_FAIL")

    decision = evaluate_runtime_batch(control_analysis, c0_analysis)
    localization_payload = c0_analysis.get("localization", {}) if c0_analysis else {}
    fractions = localization_payload.get("category_energy_fraction", {})
    for key, marker in (("constraint_lm", "CONSTRAINT_LM_ENERGY_FRACTION"), ("electron_potential", "ELECTRON_POTENTIAL_ENERGY_FRACTION"), ("other", "OTHER_ENERGY_FRACTION")):
        value = _finite_or_none(fractions.get(key))
        if value is not None:
            print(f"ISSUE46_JAC_LOCALIZATION_{marker}: {value:.12e}")

    if c0_analysis is not None:
        c0_worst = _finite_or_none(c0_analysis.get("jacobian", {}).get("worst_relative_frobenius_error"))
        print("ISSUE46_JAC_LOCALIZATION_C0_LOCALIZATION: " + f"{c0_analysis.get('status', 'HOLD')}")
        if c0_worst is not None:
            print(f"ISSUE46_JAC_LOCALIZATION_C0_JACOBIAN_REL_ERROR: {c0_worst:.12e}")
        mapped = localization_payload.get("mapped_entry_count")
        if mapped is not None:
            print(f"ISSUE46_JAC_LOCALIZATION_C0_MAPPED_DIFFERENCE_ENTRIES: {mapped}")

    summary = {
        "issue": ISSUE,
        "mode": "augmented-jacobian-localization-runtime",
        "status": decision["status"],
        "p3_executed": True,
        "evr_count_for_this_batch": 1,
        "evr_budget_owner": "#46",
        "batch_members": {
            "framework_control": {"executed": True, "run": control_run, "analysis": control_analysis},
            "c0_localization": {"executed": c0_run is not None, "run": c0_run, "dofmap": str(dofmap_path) if dofmap_path.is_file() else None, "analysis": c0_analysis, "skip_reason": None if c0_run is not None else "framework control did not pass its Jacobian contract"},
        },
        "preflight": {"status": preflight_status, "p1": {"c0_localization": prepared["p1_main"], "framework_control": prepared["p1_control"]}, "p2": {"c0_check_input": p2_main, "framework_control_check_input": p2_control}},
        "contracts": {"target": TARGET, "localization_threshold": LOCALIZATION_THRESHOLD, "global_jacobian_rel_tol": GLOBAL_JACOBIAN_REL_TOL, "framework_control_rel_tol": FRAMEWORK_CONTROL_REL_TOL, "dominant_energy_fraction": DOMINANT_ENERGY_FRACTION, "control_fail_fast": True},
        "decision": decision,
    }
    summary_path = prepared["root"] / "summary.json"
    _write_json(summary_path, summary)

    print("ISSUE46_JAC_LOCALIZATION_PRECLASS: " + ("PASS" if decision["status"] == "PASS" else "HOLD"))
    print(f"ISSUE46_JAC_LOCALIZATION_CLASS: {decision['class']}")
    print(f"ISSUE46_JAC_LOCALIZATION_REASON: {decision['reason']}")
    print(f"ISSUE46_JAC_LOCALIZATION_CONTROL_LOG: {control_log}")
    if c0_run is not None:
        print(f"ISSUE46_JAC_LOCALIZATION_C0_LOG: {c0_run['log']}")
    if dofmap_path.is_file():
        print(f"ISSUE46_JAC_LOCALIZATION_DOFMAP: {dofmap_path}")
    print(f"ISSUE46_JAC_LOCALIZATION_SUMMARY: {summary_path}")
    return 0 if decision["status"] == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Issue46 augmented Jacobian localization audit")
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--run", action="store_true", help="execute the explicitly authorized one-EVR framework-control + C0 batch")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    try:
        if args.preflight:
            return run_preflight(args.qpx, args.results_root)
        return run_runtime(args.qpx, args.results_root)
    except (Issue46JacobianLocalizationError, inv.ElectronInventoryNullspaceError, MooseInputError, mb.MooseBlockError, mp.MooseParameterError, dm.DofMapError, pm.MatrixParseError, po.PetscOptionsError, OSError) as exc:
        marker = "ISSUE46_JAC_LOCALIZATION_PREFLIGHT" if args.preflight else "ISSUE46_JAC_LOCALIZATION_PRECLASS"
        print(f"{marker}: HOLD")
        print("ISSUE46_JAC_LOCALIZATION_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(f"ISSUE46_JAC_LOCALIZATION_REASON: {exc}")
        return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
