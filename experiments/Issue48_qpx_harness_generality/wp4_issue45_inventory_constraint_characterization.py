#!/usr/bin/env python3
"""P0 characterization for the historical Issue45 inventory-constraint contract."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.historical_recipe_support import issue45_inventory_constraint as recipe


C0_TARGET = 1.0e16
C1_TARGET = 1.01e16
DEFAULT_MACRO_ELECTRON_AVG = 1.0e16
LAMBDA_VARIABLE = "r45_inventory_lambda"


def _synthetic_feedback_input() -> str:
    boundaries = " ".join(sorted(recipe.EXPECTED_DRIFT_BOUNDARIES))
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
    type = {recipe.DRIFT_TYPE}
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
[Postprocessors]
[]
[Executioner]
  type = Transient
  dt = 1e-13
  end_time = 1e-13
[]
[Outputs]
  [out]
    type = CSV
  []
  [console]
    type = Console
  []
[]
"""


def _synthetic_constrained_input(
    macro_avg: float = DEFAULT_MACRO_ELECTRON_AVG,
) -> str:
    """Frozen pre-retirement canonical structure fixture."""
    boundaries = " ".join(sorted(recipe.EXPECTED_DRIFT_BOUNDARIES))
    return f"""[Variables]
  [n_e]
    type = MooseVariableFVReal
  []
  [potential_plasma]
    type = MooseVariableFVReal
  []
  [{LAMBDA_VARIABLE}]
    type = MooseVariableScalar
  []
[]
[FVKernels]
  [diffusion]
    type = FVDiffusion
    variable = n_e
  []
  [drift]
    type = {recipe.DRIFT_TYPE}
    variable = n_e
    boundaries_to_avoid = '{boundaries}'
  []
  [phi]
    type = FVDiffusion
    variable = potential_plasma
  []
  [inventory_constraint]
    type = {recipe.CONSTRAINT_TYPE}
    variable = n_e
    lambda = {LAMBDA_VARIABLE}
    phi0 = {recipe.MACRO_AVG_POSTPROCESSOR}
    block = plasma
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
[Postprocessors]
  [{recipe.MACRO_AVG_POSTPROCESSOR}]
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


def _synthetic_runtime_row(target: float) -> dict[str, float]:
    """Frozen pre-retirement runtime observation vector."""
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


def _good_diag() -> dict[str, object]:
    return {
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


def _check_constants() -> None:
    frozen = {
        "C0_TARGET": C0_TARGET,
        "C1_TARGET": C1_TARGET,
        "DEFAULT_MACRO_ELECTRON_AVG": DEFAULT_MACRO_ELECTRON_AVG,
        "LAMBDA_VARIABLE": LAMBDA_VARIABLE,
    }
    for name, expected in frozen.items():
        if getattr(recipe, name) != expected:
            raise AssertionError(f"Issue45 inventory constant drift: {name}")


def _check_construction() -> None:
    for target in (C0_TARGET, C1_TARGET):
        text = recipe.build_constrained_quasisteady_input(
            _synthetic_feedback_input(),
            macro_avg=target,
            runtime_observability=True,
        )
        audit = recipe.audit_constrained_quasisteady_structure(
            text, expected_macro_avg=target
        )
        if audit["status"] != "PASS":
            raise AssertionError(f"constrained construction failed for target {target}: {audit['blockers']}")
        if audit["constraint"]["target_macro_average"] != target:
            raise AssertionError("constrained construction target metadata drift")
        if "FVTimeKernel" in [item.get("type") for item in audit["electron_kernels"]]:
            raise AssertionError("constrained construction retained physical time kernel")


def _check_structure_policy() -> None:
    constrained = _synthetic_constrained_input()
    cases = {
        "positive": (constrained, "PASS", set()),
        "retained-time-kernel": (
            constrained.replace(
                "[FVKernels]\n",
                "[FVKernels]\n  [time]\n    type = FVTimeKernel\n    variable = n_e\n  []\n",
                1,
            ),
            "HOLD",
            {"quasisteady-electron-kernel-set", "fvtimekernel-removed"},
        ),
        "wrong-target": (
            constrained.replace(
                f"value = {DEFAULT_MACRO_ELECTRON_AVG:.17g}",
                "value = 2e16",
                1,
            ),
            "HOLD",
            {"macro-average-target-preserved"},
        ),
        "wrong-lambda": (
            constrained.replace(
                f"lambda = {LAMBDA_VARIABLE}",
                "lambda = missing_lambda",
                1,
            ),
            "HOLD",
            {"constraint-couples-scalar-lambda"},
        ),
    }
    for name, (text, expected_status, required_blockers) in cases.items():
        result = recipe.audit_constrained_quasisteady_structure(
            text, expected_macro_avg=DEFAULT_MACRO_ELECTRON_AVG
        )
        if result["status"] != expected_status:
            raise AssertionError(f"structure:{name} status drift: {result['status']}")
        blocker_ids = {item["id"] for item in result.get("blockers", [])}
        if not required_blockers.issubset(blocker_ids):
            raise AssertionError(
                f"structure:{name} blocker drift: {blocker_ids} lacks {required_blockers}"
            )


def _check_pair_policy() -> None:
    c0 = _synthetic_constrained_input(C0_TARGET)
    c1 = _synthetic_constrained_input(C1_TARGET)
    positive = recipe.target_only_pair_audit(c0, c1)
    if positive != {
        "status": "PASS",
        "class": "TARGET_ONLY_PAIR_PASS",
        "reason": "C0/C1 inputs are byte-identical after normalizing the declared macro electron-average target",
    }:
        raise AssertionError(f"target-only positive contract drift: {positive}")
    mutated = recipe.target_only_pair_audit(
        c0, c1.replace("boundary = outlet", "boundary = plasma_cover", 1)
    )
    if mutated["status"] != "HOLD" or mutated["class"] != "PAIR_CONSTRUCTION_MISMATCH":
        raise AssertionError(f"target-only mutation contract drift: {mutated}")


def _check_runtime_policy() -> None:
    good_diag = _good_diag()
    bad_row = _synthetic_runtime_row(C1_TARGET)
    bad_row["n_avg"] = C1_TARGET * 1.001
    bad_row["inventory"] = bad_row["n_avg"] * bad_row["domain_volume"]
    cases = {
        "positive": (
            {
                "target": C0_TARGET,
                "returncode": 0,
                "converged_marker": True,
                "diagnostic": good_diag,
                "row": _synthetic_runtime_row(C0_TARGET),
            },
            "PASS",
            "CONSTRAINED_STEADY_CASE_PASS",
        ),
        "target-tracking": (
            {
                "target": C1_TARGET,
                "returncode": 0,
                "converged_marker": True,
                "diagnostic": good_diag,
                "row": bad_row,
            },
            "HOLD",
            "CONSTRAINT_TARGET_TRACKING_FAIL",
        ),
        "zero-pivot": (
            {
                "target": C0_TARGET,
                "returncode": 1,
                "converged_marker": False,
                "diagnostic": {
                    **good_diag,
                    "pc_failure_reason": "FACTOR_NUMERIC_ZEROPIVOT",
                },
                "row": None,
            },
            "HOLD",
            "SECONDARY_SINGULAR_MODE_SUSPECTED",
        ),
        "missing-residuals": (
            {
                "target": C0_TARGET,
                "returncode": 0,
                "converged_marker": True,
                "diagnostic": {**good_diag, "variable_residuals": []},
                "row": _synthetic_runtime_row(C0_TARGET),
            },
            "HOLD",
            "CLOSURE_EVIDENCE_INSUFFICIENT",
        ),
    }
    for name, (kwargs, expected_status, expected_class) in cases.items():
        result = recipe.evaluate_runtime_case_data(**kwargs)
        if result.get("status") != expected_status or result.get("class") != expected_class:
            raise AssertionError(f"runtime-case:{name} drift: {result}")

    c0 = recipe.evaluate_runtime_case_data(
        target=C0_TARGET,
        returncode=0,
        converged_marker=True,
        diagnostic=good_diag,
        row=_synthetic_runtime_row(C0_TARGET),
    )
    c1 = recipe.evaluate_runtime_case_data(
        target=C1_TARGET,
        returncode=0,
        converged_marker=True,
        diagnostic=good_diag,
        row=_synthetic_runtime_row(C1_TARGET),
    )
    pair = recipe.evaluate_runtime_pair(c0, c1, target0=C0_TARGET, target1=C1_TARGET)
    if pair.get("status") != "PASS" or pair.get("class") != "CONSTRAINED_QUASISTEADY_RUNTIME_PASS":
        raise AssertionError(f"runtime-pair positive contract drift: {pair}")


def _check_primitive_boundary() -> None:
    source = Path(recipe.__file__).read_text()
    for required in (
        "from physics_harness.adapters.moose import blocks as mb",
        "from physics_harness.adapters.moose import parameters as mp",
        "from physics_harness.adapters.moose.preflight import validate_parser_symbols_text",
    ):
        if required not in source:
            raise AssertionError(f"missing generic primitive import: {required}")
    if "qpx_harness" in source:
        raise AssertionError("legacy production dependency leaked into Issue45 recipe")

    for relative in (
        "physics_harness/domains/plasma/electron_inventory.py",
        "physics_harness/analysis/electron_inventory",
        "physics_harness/adapters/moose/electron_inventory",
        "physics_harness/execution/electron_inventory",
        "physics_harness/cli/commands/inventory.py",
    ):
        if (ROOT / relative).exists():
            raise AssertionError(f"retired production electron-inventory owner resurrected: {relative}")


def main() -> int:
    try:
        _check_constants()
        _check_construction()
        print("ISSUE48_WP4_ISSUE45_INVENTORY_CHECK: construction=PASS")
        _check_structure_policy()
        print("ISSUE48_WP4_ISSUE45_INVENTORY_CHECK: structure-policy=PASS")
        _check_pair_policy()
        print("ISSUE48_WP4_ISSUE45_INVENTORY_CHECK: target-pair-policy=PASS")
        _check_runtime_policy()
        print("ISSUE48_WP4_ISSUE45_INVENTORY_CHECK: runtime-policy=PASS")
        _check_primitive_boundary()
        print("ISSUE48_WP4_ISSUE45_INVENTORY_CHECK: recipe-reverse-dependency=NONE")
    except Exception as exc:
        print(f"ISSUE48_WP4_ISSUE45_INVENTORY_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP4_ISSUE45_INVENTORY_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
