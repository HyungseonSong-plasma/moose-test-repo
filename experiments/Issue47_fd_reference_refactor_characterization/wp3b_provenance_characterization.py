#!/usr/bin/env python3
"""WP-3B post-refactor characterization of Issue46 framework-control provenance."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics_harness.adapters.moose.input import MooseInput
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose import petsc_options as po


REFERENCE_REVISION = "9f388366ccf"
FRAMEWORK_CONTROL_REL_TOL = 5.0e-8


def _build_framework_control_input() -> str:
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


def _audit_framework_control_structure(text: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, observed: Any, required: Any) -> None:
        checks.append(
            {
                "id": name,
                "status": "PASS" if ok else "FAIL",
                "observed": observed,
                "required": required,
            }
        )

    MooseInput(text)
    get = lambda path, name: mp.unquote(mp.get_parameter(text, path, name))
    add("mesh-type", get("Mesh", "type") == "GeneratedMesh", get("Mesh", "type"), "GeneratedMesh")
    add("mesh-dim", get("Mesh", "dim") == "1", get("Mesh", "dim"), "1")
    add(
        "fv-variable",
        get("Variables/v", "type") == "MooseVariableFVReal",
        get("Variables/v", "type"),
        "MooseVariableFVReal",
    )
    add(
        "fv-boundary-expansion",
        get("Variables/v", "two_term_boundary_expansion") == "false",
        get("Variables/v", "two_term_boundary_expansion"),
        "false",
    )
    add(
        "scalar-family",
        get("Variables/lambda", "family") == "SCALAR",
        get("Variables/lambda", "family"),
        "SCALAR",
    )
    add(
        "scalar-order",
        get("Variables/lambda", "order") == "FIRST",
        get("Variables/lambda", "order"),
        "FIRST",
    )

    kernel_paths = mp.direct_children(text, "FVKernels")
    expected_kernels = {"FVKernels/diffusion", "FVKernels/lambda_constraint"}
    add(
        "control-kernel-set",
        set(kernel_paths) == expected_kernels,
        kernel_paths,
        sorted(expected_kernels),
    )
    diffusion_type = (
        get("FVKernels/diffusion", "type")
        if "FVKernels/diffusion" in kernel_paths
        else None
    )
    diffusion_variable = (
        get("FVKernels/diffusion", "variable")
        if "FVKernels/diffusion" in kernel_paths
        else None
    )
    diffusion_coeff = (
        get("FVKernels/diffusion", "coeff")
        if "FVKernels/diffusion" in kernel_paths
        else None
    )
    add("control-diffusion-type", diffusion_type == "FVDiffusion", diffusion_type, "FVDiffusion")
    add("control-diffusion-variable", diffusion_variable == "v", diffusion_variable, "v")
    add("control-diffusion-coeff", diffusion_coeff == "1", diffusion_coeff, "1")
    all_kernel_types = [get(path, "type") for path in kernel_paths]
    add(
        "no-moose-testapp-fvelementaladvection",
        "FVElementalAdvection" not in all_kernel_types,
        all_kernel_types,
        "FVElementalAdvection absent",
    )

    add(
        "control-constraint-type",
        get("FVKernels/lambda_constraint", "type") == "FVIntegralValueConstraint",
        get("FVKernels/lambda_constraint", "type"),
        "FVIntegralValueConstraint",
    )
    add(
        "control-constraint-variable",
        get("FVKernels/lambda_constraint", "variable") == "v",
        get("FVKernels/lambda_constraint", "variable"),
        "v",
    )
    add(
        "control-constraint-lambda",
        get("FVKernels/lambda_constraint", "lambda") == "lambda",
        get("FVKernels/lambda_constraint", "lambda"),
        "lambda",
    )
    add(
        "control-constraint-phi0",
        get("FVKernels/lambda_constraint", "phi0") == "1",
        get("FVKernels/lambda_constraint", "phi0"),
        "1",
    )
    add(
        "control-steady",
        get("Executioner", "type") == "Steady",
        get("Executioner", "type"),
        "Steady",
    )
    add(
        "control-newton",
        get("Executioner", "solve_type") == "NEWTON",
        get("Executioner", "solve_type"),
        "NEWTON",
    )
    add(
        "control-auto-scaling",
        get("Executioner", "automatic_scaling") == "true",
        get("Executioner", "automatic_scaling"),
        "true",
    )
    add(
        "control-offdiag-scaling",
        get("Executioner", "off_diagonals_in_auto_scaling") == "true",
        get("Executioner", "off_diagonals_in_auto_scaling"),
        "true",
    )
    flags = po.get_flags(text)
    add(
        "control-jacobian-observability",
        "-snes_test_jacobian" in flags,
        flags,
        "-snes_test_jacobian",
    )
    pairs = po.get_name_value_pairs(text)
    expected_pairs = [("-pc_type", "lu"), ("-pc_factor_shift_type", "NONZERO")]
    add("control-lu-nonzero", pairs == expected_pairs, pairs, expected_pairs)

    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": (
            "MOOSE_CONSTRAINT_CONTROL_STRUCTURE_PASS"
            if not blockers
            else "MOOSE_CONSTRAINT_CONTROL_STRUCTURE_FAIL"
        ),
        "checks": checks,
        "blockers": blockers,
        "source_contract": {
            "reference_source": {
                "project": "MOOSE",
                "revision": REFERENCE_REVISION,
                "purpose": "framework-control source contract",
            },
            "runtime_identity": "OBSERVED_SEPARATELY",
            "control_operator": "FVDiffusion",
            "control_operator_registration": "MooseApp",
            "rejected_test_only_operator": "FVElementalAdvection",
            "official_constraint_regression_ratio_tol": FRAMEWORK_CONTROL_REL_TOL,
            "runtime_jacobian_execution_deferred_to_p3": True,
        },
    }


def main() -> int:
    try:
        report = _audit_framework_control_structure(_build_framework_control_input())
        if report.get("status") != "PASS":
            raise AssertionError("framework-control structure is not PASS")

        source = report.get("source_contract", {})
        if "moose_commit" in source:
            raise AssertionError("ambiguous moose_commit provenance key still exists")

        reference = source.get("reference_source", {})
        if reference.get("project") != "MOOSE":
            raise AssertionError("reference-source project is not MOOSE")
        if reference.get("revision") != REFERENCE_REVISION:
            raise AssertionError("reference-source revision drifted")
        if reference.get("purpose") != "framework-control source contract":
            raise AssertionError("reference-source purpose is not explicit")

        if source.get("runtime_identity") != "OBSERVED_SEPARATELY":
            raise AssertionError(
                "runtime identity is not explicitly separated from reference source"
            )
    except Exception as exc:
        print(f"ISSUE47_WP3B_PROVENANCE_CHARACTERIZATION: FAIL ({exc})")
        return 1

    print("ISSUE47_WP3B_PROVENANCE_CHECK: framework-control-structure=PASS")
    print("ISSUE47_WP3B_PROVENANCE_CHECK: ambiguous-moose-commit-reference=REMOVED")
    print("ISSUE47_WP3B_PROVENANCE_CHECK: reference-source-explicit=PASS")
    print("ISSUE47_WP3B_PROVENANCE_CHECK: runtime-identity-separate=PASS")
    print("ISSUE47_WP3B_PROVENANCE_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
