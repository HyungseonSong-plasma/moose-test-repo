"""Issue46 augmented electron-inventory Jacobian block-localization harness.

This module owns P0/P1/P2 construction for the #46 successor.  Preflight never
executes the C0 localization solve or the known-good Jacobian runtime control;
those belong to one later, explicitly authorized P3 batch so user-local runtime
evidence is not spent during construction.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

from . import electron_inventory_nullspace as inv
from . import evidence
from . import fast_plasma_coupling_diagnostic as coupling_diag
from . import fast_plasma_relaxation_v2 as v2
from . import petsc_first_linear_diagnostic as first_linear
from .moose_input import MooseInput, MooseInputError
from .runtime import run_qpx

ISSUE = 46
TARGET = inv.C0_TARGET
LOCALIZATION_THRESHOLD = 1.0e-7
GLOBAL_JACOBIAN_REL_TOL = first_linear.JACOBIAN_REL_TOL
FRAMEWORK_CONTROL_REL_TOL = 5.0e-8
DOMINANT_ENERGY_FRACTION = 0.80
DOFMAP_OUTPUT = "r46_dofmap"
DOFMAP_FILE_BASE = "r46_dofmap"
MAIN_VARIABLES = ("n_e", "potential_plasma", inv.LAMBDA_VARIABLE)
SCALAR_VARIABLES = (inv.LAMBDA_VARIABLE,)


class AugmentedJacobianLocalizationError(RuntimeError):
    pass


def _petsc_name_value_pairs(text: str) -> list[tuple[str, str]]:
    names = inv._words(inv._parameter_value(text, "Executioner", "petsc_options_iname"))
    values = inv._words(inv._parameter_value(text, "Executioner", "petsc_options_value"))
    if len(names) != len(values):
        raise AugmentedJacobianLocalizationError(
            f"petsc_options_iname/value length mismatch: {len(names)} != {len(values)}"
        )
    return list(zip(names, values))


def _set_petsc_name_value_pairs(text: str, pairs: list[tuple[str, str]]) -> str:
    names = " ".join(name for name, _ in pairs)
    values = " ".join(value for _, value in pairs)
    out = inv._set_or_insert_parameter(text, "Executioner", "petsc_options_iname", f"'{names}'")
    return inv._set_or_insert_parameter(out, "Executioner", "petsc_options_value", f"'{values}'")


def _upsert_petsc_value(text: str, name: str, value: str) -> str:
    pairs = _petsc_name_value_pairs(text)
    out: list[tuple[str, str]] = []
    replaced = False
    for existing_name, existing_value in pairs:
        if existing_name == name:
            if replaced:
                raise AugmentedJacobianLocalizationError(f"duplicate PETSc option {name}")
            out.append((name, value))
            replaced = True
        else:
            out.append((existing_name, existing_value))
    if not replaced:
        out.append((name, value))
    return _set_petsc_name_value_pairs(text, out)


def _set_petsc_flags(text: str, flags: list[str]) -> str:
    return inv._set_or_insert_parameter(
        text, "Executioner", "petsc_options", "'" + " ".join(flags) + "'"
    )


def _add_dofmap_output(text: str) -> str:
    children = inv._direct_children(text, "Outputs")
    path = f"Outputs/{DOFMAP_OUTPUT}"
    if path in children:
        raise AugmentedJacobianLocalizationError(f"output block already exists: {path}")
    block = (
        f"  [{DOFMAP_OUTPUT}]\n"
        "    type = DOFMap\n"
        "    execute_on = INITIAL\n"
        f"    file_base = {DOFMAP_FILE_BASE}\n"
        "  []"
    )
    try:
        out = MooseInput(text).insert_before_close("Outputs", block)[0]
        MooseInput(out)
        return out
    except MooseInputError as exc:
        raise AugmentedJacobianLocalizationError(f"failed to add DOFMap output: {exc}") from exc


def instrument_localization(first_linear_text: str) -> tuple[str, dict[str, Any]]:
    flags = first_linear._petsc_options(first_linear_text)
    flags = [flag for flag in flags if flag != "-snes_test_jacobian"]
    if "-snes_test_jacobian_view" not in flags:
        flags.append("-snes_test_jacobian_view")
    out = _set_petsc_flags(first_linear_text, flags)
    out = _upsert_petsc_value(out, "-snes_test_jacobian", f"{LOCALIZATION_THRESHOLD:.12g}")
    out = _add_dofmap_output(out)
    MooseInput(out)
    return out, {
        "target": TARGET,
        "localization_threshold": LOCALIZATION_THRESHOLD,
        "dofmap_output": DOFMAP_OUTPUT,
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "scaling_policy_changed": False,
        "diagnostic_observability_only": True,
    }


def _remove_optional_block(text: str, path: str) -> str:
    if not MooseInput(text).find(path):
        return text
    return inv._remove_block(text, path)


def _normalized_localization_text(text: str) -> str:
    out = _remove_optional_block(text, f"Outputs/{DOFMAP_OUTPUT}")
    out = inv._set_or_insert_parameter(out, "Executioner", "petsc_options", "'<PETSC_FLAGS>'")
    out = inv._set_or_insert_parameter(out, "Executioner", "petsc_options_iname", "'<PETSC_INAMES>'")
    out = inv._set_or_insert_parameter(out, "Executioner", "petsc_options_value", "'<PETSC_VALUES>'")
    return out


def audit_localization_structure(base_first_linear: str, localization_text: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, observed: Any, required: Any) -> None:
        checks.append(
            {"id": name, "status": "PASS" if ok else "FAIL", "observed": observed, "required": required}
        )

    closure = inv.audit_constrained_quasisteady_structure(
        localization_text, expected_macro_avg=TARGET
    )
    add("canonical-c0-closure-structure", closure["status"] == "PASS", closure["status"], "PASS")

    nl_max = inv._unquote(inv._parameter_value(localization_text, "Executioner", "nl_max_its"))
    add("first-linear-horizon-preserved", nl_max == "1", nl_max, "1")

    expected_flags = [
        flag for flag in first_linear._petsc_options(base_first_linear)
        if flag != "-snes_test_jacobian"
    ]
    if "-snes_test_jacobian_view" not in expected_flags:
        expected_flags.append("-snes_test_jacobian_view")
    actual_flags = first_linear._petsc_options(localization_text)
    add("localization-petsc-flags-exact", actual_flags == expected_flags, actual_flags, expected_flags)

    base_pairs = _petsc_name_value_pairs(base_first_linear)
    expected_pairs = list(base_pairs) + [("-snes_test_jacobian", f"{LOCALIZATION_THRESHOLD:.12g}")]
    actual_pairs = _petsc_name_value_pairs(localization_text)
    add("localization-threshold-pair-exact", actual_pairs == expected_pairs, actual_pairs, expected_pairs)

    output_path = f"Outputs/{DOFMAP_OUTPUT}"
    outputs = inv._direct_children(localization_text, "Outputs")
    add("one-localization-dofmap-output", outputs.count(output_path) == 1, outputs, output_path)
    if output_path in outputs:
        dof_type = inv._unquote(inv._parameter_value(localization_text, output_path, "type"))
        dof_execute = inv._words(inv._parameter_value(localization_text, output_path, "execute_on"))
        dof_base = inv._unquote(inv._parameter_value(localization_text, output_path, "file_base"))
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
        checks.append(
            {"id": name, "status": "PASS" if ok else "FAIL", "observed": observed, "required": required}
        )

    MooseInput(text)
    add("mesh-type", inv._unquote(inv._parameter_value(text, "Mesh", "type")) == "GeneratedMesh", inv._unquote(inv._parameter_value(text, "Mesh", "type")), "GeneratedMesh")
    add("mesh-dim", inv._unquote(inv._parameter_value(text, "Mesh", "dim")) == "1", inv._unquote(inv._parameter_value(text, "Mesh", "dim")), "1")
    add("fv-variable", inv._unquote(inv._parameter_value(text, "Variables/v", "type")) == "MooseVariableFVReal", inv._unquote(inv._parameter_value(text, "Variables/v", "type")), "MooseVariableFVReal")
    add("fv-boundary-expansion", inv._unquote(inv._parameter_value(text, "Variables/v", "two_term_boundary_expansion")) == "false", inv._unquote(inv._parameter_value(text, "Variables/v", "two_term_boundary_expansion")), "false")
    add("scalar-family", inv._unquote(inv._parameter_value(text, "Variables/lambda", "family")) == "SCALAR", inv._unquote(inv._parameter_value(text, "Variables/lambda", "family")), "SCALAR")
    add("scalar-order", inv._unquote(inv._parameter_value(text, "Variables/lambda", "order")) == "FIRST", inv._unquote(inv._parameter_value(text, "Variables/lambda", "order")), "FIRST")

    kernel_paths = inv._direct_children(text, "FVKernels")
    add("control-kernel-set", set(kernel_paths) == {"FVKernels/diffusion", "FVKernels/lambda_constraint"}, kernel_paths, ["FVKernels/diffusion", "FVKernels/lambda_constraint"])
    diffusion_type = inv._unquote(inv._parameter_value(text, "FVKernels/diffusion", "type")) if "FVKernels/diffusion" in kernel_paths else None
    diffusion_variable = inv._unquote(inv._parameter_value(text, "FVKernels/diffusion", "variable")) if "FVKernels/diffusion" in kernel_paths else None
    diffusion_coeff = inv._unquote(inv._parameter_value(text, "FVKernels/diffusion", "coeff")) if "FVKernels/diffusion" in kernel_paths else None
    add("control-diffusion-type", diffusion_type == "FVDiffusion", diffusion_type, "FVDiffusion")
    add("control-diffusion-variable", diffusion_variable == "v", diffusion_variable, "v")
    add("control-diffusion-coeff", diffusion_coeff == "1", diffusion_coeff, "1")
    all_kernel_types = [
        inv._unquote(inv._parameter_value(text, path, "type")) for path in kernel_paths
    ]
    add("no-moose-testapp-fvelementaladvection", "FVElementalAdvection" not in all_kernel_types, all_kernel_types, "FVElementalAdvection absent")

    add("control-constraint-type", inv._unquote(inv._parameter_value(text, "FVKernels/lambda_constraint", "type")) == "FVIntegralValueConstraint", inv._unquote(inv._parameter_value(text, "FVKernels/lambda_constraint", "type")), "FVIntegralValueConstraint")
    add("control-constraint-variable", inv._unquote(inv._parameter_value(text, "FVKernels/lambda_constraint", "variable")) == "v", inv._unquote(inv._parameter_value(text, "FVKernels/lambda_constraint", "variable")), "v")
    add("control-constraint-lambda", inv._unquote(inv._parameter_value(text, "FVKernels/lambda_constraint", "lambda")) == "lambda", inv._unquote(inv._parameter_value(text, "FVKernels/lambda_constraint", "lambda")), "lambda")
    add("control-constraint-phi0", inv._unquote(inv._parameter_value(text, "FVKernels/lambda_constraint", "phi0")) == "1", inv._unquote(inv._parameter_value(text, "FVKernels/lambda_constraint", "phi0")), "1")
    add("control-steady", inv._unquote(inv._parameter_value(text, "Executioner", "type")) == "Steady", inv._unquote(inv._parameter_value(text, "Executioner", "type")), "Steady")
    add("control-newton", inv._unquote(inv._parameter_value(text, "Executioner", "solve_type")) == "NEWTON", inv._unquote(inv._parameter_value(text, "Executioner", "solve_type")), "NEWTON")
    add("control-auto-scaling", inv._truthy(inv._parameter_value(text, "Executioner", "automatic_scaling")), inv._unquote(inv._parameter_value(text, "Executioner", "automatic_scaling")), "true")
    add("control-offdiag-scaling", inv._truthy(inv._parameter_value(text, "Executioner", "off_diagonals_in_auto_scaling")), inv._unquote(inv._parameter_value(text, "Executioner", "off_diagonals_in_auto_scaling")), "true")
    flags = first_linear._petsc_options(text)
    add("control-jacobian-observability", "-snes_test_jacobian" in flags, flags, "-snes_test_jacobian")
    pairs = _petsc_name_value_pairs(text)
    add("control-lu-nonzero", pairs == [("-pc_type", "lu"), ("-pc_factor_shift_type", "NONZERO")], pairs, [("-pc_type", "lu"), ("-pc_factor_shift_type", "NONZERO")])
    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": "MOOSE_CONSTRAINT_CONTROL_STRUCTURE_PASS" if not blockers else "MOOSE_CONSTRAINT_CONTROL_STRUCTURE_FAIL",
        "checks": checks,
        "blockers": blockers,
        "source_contract": {
            "moose_commit": "9f388366ccf",
            "control_operator": "FVDiffusion",
            "control_operator_registration": "MooseApp",
            "rejected_test_only_operator": "FVElementalAdvection",
            "official_constraint_regression_ratio_tol": FRAMEWORK_CONTROL_REL_TOL,
            "runtime_jacobian_execution_deferred_to_p3": True,
        },
    }


def parse_dof_map_text(
    text: str,
    *,
    expected_variables: tuple[str, ...] = MAIN_VARIABLES,
    scalar_variables: tuple[str, ...] = SCALAR_VARIABLES,
) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AugmentedJacobianLocalizationError(f"invalid DOFMap JSON: {exc}") from exc
    ndof = payload.get("ndof")
    vars_payload = payload.get("vars")
    if not isinstance(ndof, int) or ndof <= 0 or not isinstance(vars_payload, list):
        raise AugmentedJacobianLocalizationError("DOFMap JSON lacks positive ndof or vars list")

    by_name: dict[str, set[int]] = {name: set() for name in expected_variables}
    seen_names: set[str] = set()
    for item in vars_payload:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        name = item["name"]
        if name not in by_name:
            continue
        seen_names.add(name)
        for subdomain in item.get("subdomains", []):
            if not isinstance(subdomain, dict):
                continue
            for dof in subdomain.get("dofs", []):
                if isinstance(dof, int):
                    by_name[name].add(dof)
    missing_names = [name for name in expected_variables if name not in seen_names]
    if missing_names:
        raise AugmentedJacobianLocalizationError(f"DOFMap missing variables: {missing_names}")

    for name, dofs in by_name.items():
        invalid = sorted(dof for dof in dofs if dof < 0 or dof >= ndof)
        if invalid:
            raise AugmentedJacobianLocalizationError(f"DOFMap variable {name} has invalid DOFs: {invalid[:8]}")

    owner: dict[int, str] = {}
    overlaps: list[tuple[int, str, str]] = []
    for name, dofs in by_name.items():
        for dof in dofs:
            prior = owner.get(dof)
            if prior is not None and prior != name:
                overlaps.append((dof, prior, name))
            owner[dof] = name
    if overlaps:
        raise AugmentedJacobianLocalizationError(f"DOFMap variable overlap: {overlaps[:8]}")

    unmapped = sorted(set(range(ndof)) - set(owner))
    empty_scalars = [name for name in scalar_variables if not by_name.get(name)]
    if empty_scalars:
        if len(empty_scalars) == 1 and len(unmapped) == 1:
            scalar = empty_scalars[0]
            by_name[scalar].add(unmapped[0])
            owner[unmapped[0]] = scalar
            unmapped = []
        else:
            raise AugmentedJacobianLocalizationError(
                f"cannot resolve scalar DOFs: scalars={empty_scalars}, unmapped={unmapped[:8]}"
            )
    if unmapped:
        raise AugmentedJacobianLocalizationError(f"DOFMap has unmapped nonlinear DOFs: {unmapped[:8]}")

    return {
        "ndof": ndof,
        "variables": {name: sorted(dofs) for name, dofs in by_name.items()},
        "owner_by_dof": owner,
    }


_FLOAT = r"[+\-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?|nan|inf(?:inity)?)"


def parse_threshold_difference_matrix(text: str) -> dict[str, Any]:
    header = re.search(
        rf"Hand-coded minus finite-difference Jacobian with tolerance\s+({_FLOAT})\s+-+",
        text,
        re.IGNORECASE,
    )
    if not header:
        raise AugmentedJacobianLocalizationError("thresholded Jacobian-difference matrix header is missing")
    try:
        threshold = float(header.group(1))
    except ValueError as exc:
        raise AugmentedJacobianLocalizationError("invalid Jacobian-difference threshold") from exc

    tail = text[header.end() :]
    stop_patterns = (
        r"(?m)^\s*KSP Object:",
        r"(?m)^\s*Linear solve ",
        r"(?m)^\s*Nonlinear solve ",
        r"(?m)^\s*\|residual\|_2 of individual variables:",
        r"(?m)^\s*-+ Testing Jacobian",
    )
    stop = len(tail)
    for pattern in stop_patterns:
        match = re.search(pattern, tail)
        if match:
            stop = min(stop, match.start())
    section = tail[:stop]

    entries: list[dict[str, Any]] = []
    row_pattern = re.compile(r"(?m)^\s*row\s+(\d+)\s*:\s*(.*)$", re.IGNORECASE)
    entry_pattern = re.compile(rf"\((\d+)\s*,\s*({_FLOAT})\)", re.IGNORECASE)
    for row_match in row_pattern.finditer(section):
        row = int(row_match.group(1))
        row_text = row_match.group(2)
        for entry_match in entry_pattern.finditer(row_text):
            try:
                value = float(entry_match.group(2))
            except ValueError:
                value = math.nan
            entries.append({"row": row, "col": int(entry_match.group(1)), "value": value})
    return {"threshold": threshold, "entries": entries, "section_observed": True}


def _category(row_var: str, col_var: str) -> str:
    lm = inv.LAMBDA_VARIABLE
    if row_var == lm or col_var == lm:
        return "constraint_lm"
    if {row_var, col_var} == {"n_e", "potential_plasma"}:
        return "electron_potential"
    return "other"


def localize_difference_entries(
    difference: dict[str, Any], dof_map: dict[str, Any]
) -> dict[str, Any]:
    owner = dof_map["owner_by_dof"]
    blocks: dict[str, dict[str, Any]] = {}
    category_energy = {"constraint_lm": 0.0, "electron_potential": 0.0, "other": 0.0}
    unmapped: list[dict[str, Any]] = []
    total_energy = 0.0

    for entry in difference.get("entries", []):
        row_var = owner.get(entry["row"])
        col_var = owner.get(entry["col"])
        value = float(entry["value"])
        if row_var is None or col_var is None or not math.isfinite(value):
            unmapped.append({**entry, "row_variable": row_var, "col_variable": col_var})
            continue
        energy = value * value
        total_energy += energy
        category = _category(row_var, col_var)
        category_energy[category] += energy
        key = f"{row_var}->{col_var}"
        block = blocks.setdefault(
            key,
            {
                "row_variable": row_var,
                "col_variable": col_var,
                "count": 0,
                "sum_squared_difference": 0.0,
                "max_abs_difference": 0.0,
            },
        )
        block["count"] += 1
        block["sum_squared_difference"] += energy
        block["max_abs_difference"] = max(block["max_abs_difference"], abs(value))

    for block in blocks.values():
        block["l2_difference"] = math.sqrt(block["sum_squared_difference"])
    fractions = {
        name: (energy / total_energy if total_energy > 0 else 0.0)
        for name, energy in category_energy.items()
    }
    return {
        "blocks": blocks,
        "unmapped_entries": unmapped,
        "entry_count": len(difference.get("entries", [])),
        "mapped_entry_count": sum(block["count"] for block in blocks.values()),
        "thresholded_l2_difference": math.sqrt(total_energy),
        "category_energy_fraction": fractions,
    }


def analyze_localization_text(
    log_text: str,
    dofmap_text: str,
    *,
    framework_control_pass: bool = True,
) -> dict[str, Any]:
    if not framework_control_pass:
        return {
            "status": "HOLD",
            "class": "MOOSE_CONSTRAINT_CONTROL_FAIL",
            "reason": "the same-runtime known-good FVIntegralValueConstraint control failed its Jacobian contract",
        }

    jacobian = coupling_diag.analyze_jacobian_text(
        log_text, relative_tolerance=GLOBAL_JACOBIAN_REL_TOL
    )
    if jacobian.get("class") != "JACOBIAN_MISMATCH":
        return {
            "status": "HOLD",
            "class": "JACOBIAN_LOCALIZATION_INSUFFICIENT",
            "reason": "the historical augmented Jacobian mismatch was not reproduced in the localization log",
            "jacobian": jacobian,
        }

    try:
        dof_map = parse_dof_map_text(dofmap_text)
        difference = parse_threshold_difference_matrix(log_text)
        localized = localize_difference_entries(difference, dof_map)
    except AugmentedJacobianLocalizationError as exc:
        return {
            "status": "HOLD",
            "class": "JACOBIAN_LOCALIZATION_INSUFFICIENT",
            "reason": str(exc),
            "jacobian": jacobian,
        }

    result: dict[str, Any] = {
        "status": "PASS",
        "jacobian": jacobian,
        "dof_map": {"ndof": dof_map["ndof"], "variables": dof_map["variables"]},
        "difference": difference,
        "localization": localized,
        "dominant_energy_fraction_required": DOMINANT_ENERGY_FRACTION,
    }
    if localized["unmapped_entries"]:
        result.update(
            {
                "status": "HOLD",
                "class": "JACOBIAN_LOCALIZATION_INSUFFICIENT",
                "reason": "one or more thresholded Jacobian-difference entries could not be mapped to nonlinear variables",
            }
        )
        return result
    if localized["mapped_entry_count"] == 0:
        result.update(
            {
                "status": "HOLD",
                "class": "FD_SCALING_LIMIT_SUSPECTED",
                "reason": "global Frobenius mismatch persists but no individual difference exceeds the predeclared localization threshold; a separate FD/scaling verification is required",
            }
        )
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


def _synthetic_dof_map() -> str:
    return json.dumps(
        {
            "ndof": 5,
            "demangled": True,
            "vars": [
                {"name": "n_e", "subdomains": [{"id": 1, "kernels": [], "dofs": [0, 1]}]},
                {"name": "potential_plasma", "subdomains": [{"id": 1, "kernels": [], "dofs": [2, 3]}]},
                {"name": inv.LAMBDA_VARIABLE, "subdomains": [{"id": 1, "kernels": [], "dofs": []}]},
            ],
        }
    )


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
        "Mat Object: 1 MPI process\n"
        "  type: seqaij\n"
        + "\n".join(matrix_lines)
        + "\nLinear solve did not converge due to DIVERGED_BREAKDOWN iterations 30\n"
    )


def self_test() -> int:
    try:
        base = inv._synthetic_constrained_input(TARGET)
        first_text, _ = first_linear.instrument_first_linear(base)
        localized_text, _ = instrument_localization(first_text)
        if audit_localization_structure(first_text, localized_text)["status"] != "PASS":
            raise AssertionError("positive localization structure did not pass")
        mutated = localized_text.replace("file_base = r46_dofmap", "file_base = wrong_dofmap", 1)
        if audit_localization_structure(first_text, mutated)["status"] == "PASS":
            raise AssertionError("DOFMap output mutation was accepted")

        control = build_framework_control_input()
        if audit_framework_control_structure(control)["status"] != "PASS":
            raise AssertionError("known-good framework control structure did not pass")
        bad_control = control.replace("off_diagonals_in_auto_scaling = true", "off_diagonals_in_auto_scaling = false", 1)
        if audit_framework_control_structure(bad_control)["status"] == "PASS":
            raise AssertionError("framework-control scaling mutation was accepted")
        test_only_control = control.replace("type = FVDiffusion", "type = FVElementalAdvection", 1)
        if audit_framework_control_structure(test_only_control)["status"] == "PASS":
            raise AssertionError("MooseTestApp-only FVElementalAdvection mutation was accepted")
        wrong_coeff = control.replace("coeff = 1", "coeff = 2", 1)
        if audit_framework_control_structure(wrong_coeff)["status"] == "PASS":
            raise AssertionError("framework-control diffusion coefficient mutation was accepted")

        dofmap = _synthetic_dof_map()
        parsed = parse_dof_map_text(dofmap)
        if parsed["owner_by_dof"].get(4) != inv.LAMBDA_VARIABLE:
            raise AssertionError("scalar fallback DOF mapping failed")

        lm_log = _synthetic_localization_log([(0, 4, 2.0e-4), (4, 1, -3.0e-4)])
        if analyze_localization_text(lm_log, dofmap)["class"] != "CONSTRAINT_LM_BLOCK_MISMATCH":
            raise AssertionError("LM block mismatch did not classify")
        ep_log = _synthetic_localization_log([(0, 2, 2.0e-4), (3, 1, -3.0e-4)])
        if analyze_localization_text(ep_log, dofmap)["class"] != "ELECTRON_POTENTIAL_BLOCK_MISMATCH":
            raise AssertionError("electron-potential block mismatch did not classify")
        other_log = _synthetic_localization_log([(0, 1, 2.0e-4), (2, 3, -3.0e-4)])
        if analyze_localization_text(other_log, dofmap)["class"] != "OTHER_BLOCK_MISMATCH":
            raise AssertionError("other block mismatch did not classify")
        empty_log = _synthetic_localization_log([])
        if analyze_localization_text(empty_log, dofmap)["class"] != "FD_SCALING_LIMIT_SUSPECTED":
            raise AssertionError("empty thresholded difference did not route to FD/scaling suspicion")
        if analyze_localization_text(lm_log, dofmap, framework_control_pass=False)["class"] != "MOOSE_CONSTRAINT_CONTROL_FAIL":
            raise AssertionError("framework control failure did not take precedence")
        missing_view = lm_log.split("Hand-coded minus finite-difference", 1)[0]
        if analyze_localization_text(missing_view, dofmap)["class"] != "JACOBIAN_LOCALIZATION_INSUFFICIENT":
            raise AssertionError("missing matrix view was over-classified")
    except Exception as exc:
        print(f"ISSUE46_JAC_LOCALIZATION_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE46_JAC_LOCALIZATION_SELFTEST: PASS")
    return 0


def _prepare_cases(exe: Path, results_root: str | None) -> dict[str, Any]:
    base_case, base_text, radial_span = inv._base_case_context()
    base_c0 = inv._build_constrained_quasisteady_input(
        base_text, radial_span=radial_span, macro_avg=TARGET, runtime_observability=True
    )
    first_text, _ = first_linear.instrument_first_linear(base_c0)
    localization_text, instrumentation = instrument_localization(first_text)
    p1_main = audit_localization_structure(first_text, localization_text)

    control_text = build_framework_control_input()
    p1_control = audit_framework_control_structure(control_text)

    root = inv._evidence_root(exe=exe, results_root=results_root, stem="issue46_augmented_jacobian_localization")
    main_dir = root / "c0_localization"
    control_dir = root / "framework_control"
    v2.v1._copy_case(base_case, main_dir, localization_text)
    v2.v1._validate_assets(main_dir)
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "input.i").write_text(control_text)
    return {
        "root": root,
        "main_dir": main_dir,
        "main_input": main_dir / "input.i",
        "control_dir": control_dir,
        "control_input": control_dir / "input.i",
        "p1_main": p1_main,
        "p1_control": p1_control,
        "instrumentation": instrumentation,
    }


def _check_input(exe: Path, case_dir: Path, log_path: Path) -> dict[str, Any]:
    run = run_qpx(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=log_path,
        extra_args=("--check-input", "--color", "off"),
        stream=False,
    )
    return {
        "status": "PASS" if run.returncode == 0 else "HOLD",
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(log_path),
        "identity": {
            **evidence.identity_record(executable=exe, input_path=case_dir / "input.i"),
            "qpx_sha256": evidence.sha256_file(exe),
        },
    }


def _write_summary(prepared: dict[str, Any], p2_main: dict[str, Any], p2_control: dict[str, Any], status: str) -> Path:
    path = prepared["root"] / "summary.json"
    if prepared["p1_control"]["status"] != "PASS" or p2_control.get("status") != "PASS":
        decision_class = "HARNESS_OR_CONSTRUCTION_FAIL"
        reason = "the production-registered framework control did not pass construction/check-input preflight"
    elif status == "PASS":
        decision_class = "JACOBIAN_LOCALIZATION_READY"
        reason = "the exact C0 localization case and production-registered same-runtime framework control both pass P0/P1/P2 construction; no Jacobian runtime has been executed"
    else:
        decision_class = "HARNESS_OR_CONSTRUCTION_FAIL"
        reason = "the Issue46 localization harness did not pass all P0/P1/P2 gates"
    payload = {
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
        "instrumentation": prepared["instrumentation"],
        "p1": {"c0_localization": prepared["p1_main"], "framework_control": prepared["p1_control"]},
        "p2": {"c0_check_input": p2_main, "framework_control_check_input": p2_control},
        "framework_control_runtime": {
            "executed": False,
            "reason": "runtime Jacobian control is reserved for the same authorized P3 batch as C0 localization",
        },
        "decision": {"status": status, "class": decision_class, "reason": reason},
    }
    v2._write_json(path, payload)
    return path


def run_preflight(qpx: str | None, results_root: str | None) -> int:
    exe = v2.resolve_executable(qpx)
    v2.validate_executable(exe)
    prepared = _prepare_cases(exe, results_root)
    p1_main = prepared["p1_main"]["status"] == "PASS"
    p1_control = prepared["p1_control"]["status"] == "PASS"
    p2_main = _check_input(exe, prepared["main_dir"], prepared["root"] / "p2_c0_check_input.log") if p1_main else {}
    p2_control = _check_input(exe, prepared["control_dir"], prepared["root"] / "p2_control_check_input.log") if p1_control else {}
    status = "PASS" if p1_main and p1_control and p2_main.get("status") == "PASS" and p2_control.get("status") == "PASS" else "HOLD"
    path = _write_summary(prepared, p2_main, p2_control, status)

    print(f"ISSUE46_JAC_LOCALIZATION_P1_C0: {prepared['p1_main']['status']}")
    print(f"ISSUE46_JAC_LOCALIZATION_P1_CONTROL: {prepared['p1_control']['status']}")
    print(f"ISSUE46_JAC_LOCALIZATION_P2_C0_CHECK_INPUT: {p2_main.get('status', 'HOLD')}")
    print(f"ISSUE46_JAC_LOCALIZATION_P2_CONTROL_CHECK_INPUT: {p2_control.get('status', 'HOLD')}")
    print("ISSUE46_JAC_LOCALIZATION_P2_CONTROL_RUNTIME: DEFERRED_TO_AUTHORIZED_P3")
    print(f"ISSUE46_JAC_LOCALIZATION_PREFLIGHT: {status}")
    print("ISSUE46_JAC_LOCALIZATION_CLASS: " + ("JACOBIAN_LOCALIZATION_READY" if status == "PASS" else "HARNESS_OR_CONSTRUCTION_FAIL"))
    print(f"ISSUE46_JAC_LOCALIZATION_SUMMARY: {path}")
    return 0 if status == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Issue46 augmented Jacobian localization P0/P1/P2 preflight")
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    try:
        return run_preflight(args.qpx, args.results_root)
    except (AugmentedJacobianLocalizationError, inv.ElectronInventoryNullspaceError, MooseInputError) as exc:
        print("ISSUE46_JAC_LOCALIZATION_PREFLIGHT: HOLD")
        print("ISSUE46_JAC_LOCALIZATION_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(f"ISSUE46_JAC_LOCALIZATION_REASON: {exc}")
        return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
