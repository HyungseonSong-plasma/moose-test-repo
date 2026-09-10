#!/usr/bin/env python3
"""P0 behavior characterization for the historical Issue45 first-linear recipe."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose import petsc_options as po
from experiments.historical_recipe_support import issue45_inventory_constraint as inventory
from experiments.historical_recipe_support import issue45_first_linear as recipe


def _synthetic_constrained_input(
    macro_avg: float = inventory.DEFAULT_MACRO_ELECTRON_AVG,
) -> str:
    """Preserve the accepted pre-retirement Issue45 constrained fixture."""
    boundaries = " ".join(sorted(inventory.EXPECTED_DRIFT_BOUNDARIES))
    return f"""[Variables]
  [n_e]
    type = MooseVariableFVReal
  []
  [potential_plasma]
    type = MooseVariableFVReal
  []
  [{inventory.LAMBDA_VARIABLE}]
    type = MooseVariableScalar
  []
[]
[FVKernels]
  [diffusion]
    type = FVDiffusion
    variable = n_e
  []
  [drift]
    type = {inventory.DRIFT_TYPE}
    variable = n_e
    boundaries_to_avoid = '{boundaries}'
  []
  [phi]
    type = FVDiffusion
    variable = potential_plasma
  []
  [inventory_constraint]
    type = {inventory.CONSTRAINT_TYPE}
    variable = n_e
    lambda = {inventory.LAMBDA_VARIABLE}
    phi0 = {inventory.MACRO_AVG_POSTPROCESSOR}
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
  [{inventory.MACRO_AVG_POSTPROCESSOR}]
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


def _synthetic_log(jac_rel: float = 2.0e-9) -> str:
    return f"""---------- Testing Jacobian -------------
||J - Jfd||_F/||J||_F = {jac_rel:.12e}, ||J - Jfd||_F = 2.0e-08
    |residual|_2 of individual variables:
       n_e:                  5.0e-16
       potential_plasma:     8.0e-03
       r45_inventory_lambda: 0
  0 KSP preconditioned resid norm 8.0e-03 true resid norm 8.0e-03 ||r(i)||/||b|| 1.0e+00
 30 KSP preconditioned resid norm 1.0e-12 true resid norm 2.0e-03 ||r(i)||/||b|| 2.5e-01
Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30
KSP Object: 1 MPI process
  type: gmres
    restart=30, using modified Gram-Schmidt orthogonalization
  maximum iterations=10000, initial guess is zero
  left preconditioning
  using PRECONDITIONED norm type for convergence test
PC Object: 1 MPI process
  type: lu
    out-of-place factorization
Nonlinear solve did not converge due to DIVERGED_MAX_IT iterations 1
"""


def _check_construction() -> None:
    base = _synthetic_constrained_input(recipe.TARGET)
    text, meta = recipe.instrument_first_linear(base)

    closure = inventory.audit_constrained_quasisteady_structure(
        text,
        expected_macro_avg=recipe.TARGET,
    )
    if closure["status"] != "PASS":
        raise AssertionError("first-linear construction no longer preserves C0 closure")

    nl_max = mp.unquote(mp.get_parameter(text, "Executioner", "nl_max_its"))
    if nl_max != str(recipe.DIAGNOSTIC_NL_MAX_ITS):
        raise AssertionError(f"first-linear nonlinear horizon drifted: {nl_max}")

    expected_flags = list(recipe.REQUIRED_EXISTING_OPTIONS + recipe.FIRST_LINEAR_PETSC_OPTIONS)
    observed_flags = po.get_flags(text)
    if observed_flags != expected_flags:
        raise AssertionError(
            f"first-linear PETSc option contract drifted: {observed_flags} != {expected_flags}"
        )

    expected_meta = {
        "target": recipe.TARGET,
        "diagnostic_nl_max_its": recipe.DIAGNOSTIC_NL_MAX_ITS,
        "petsc_options_added": list(recipe.FIRST_LINEAR_PETSC_OPTIONS),
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "diagnostic_horizon_changed": True,
    }
    if meta != expected_meta:
        raise AssertionError(f"first-linear metadata drift: {meta!r}")


def _check_analysis_positive() -> None:
    result = recipe.analyze_first_linear_text(_synthetic_log(), returncode=1)
    if (
        result.get("status") != "PASS"
        or result.get("class") != "KSP_BREAKDOWN_RESIDUAL_FIDELITY_LOSS"
    ):
        raise AssertionError(f"positive first-linear class drifted: {result!r}")
    if result.get("ksp_identity") != {"ksp_type": "gmres", "restart": 30, "pc_type": "lu"}:
        raise AssertionError("positive KSP identity drifted")
    if len(result.get("true_residuals") or []) != 2:
        raise AssertionError("positive true-residual evidence drifted")
    audit = result.get("ksp_residual_audit") or {}
    if not audit.get("residual_fidelity_loss_observed"):
        raise AssertionError("reported-vs-true residual fidelity loss was not retained")
    if result.get("restart_causality") != "NOT_ESTABLISHED":
        raise AssertionError("restart chronology was promoted to causal evidence")


def _check_analysis_negative_controls() -> None:
    base = _synthetic_log()
    cases = {
        "jacobian-mismatch": (
            _synthetic_log(1.0e-3),
            "JACOBIAN_MISMATCH",
        ),
        "pc-failure": (
            base.replace(
                "Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30",
                "Linear solve did not converge due to DIVERGED_PC_FAILED iterations 0\n"
                "PC failed due to FACTOR_NUMERIC_ZEROPIVOT",
                1,
            ),
            "PC_OR_FACTORIZATION_FAIL",
        ),
        "nonfinite": (
            base.replace("n_e:                  5.0e-16", "n_e:                  nan", 1),
            "NONFINITE_FAIL",
        ),
        "missing-ksp-view": (
            base.split("KSP Object:", 1)[0],
            "DIAGNOSTIC_INSUFFICIENT",
        ),
        "linear-converged": (
            base.replace(
                "Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30",
                "Linear solve converged due to CONVERGED_RTOL iterations 17",
                1,
            ),
            "FIRST_LINEAR_BEHAVIOR_CHANGED",
        ),
    }

    for name, (text, expected_class) in cases.items():
        result = recipe.analyze_first_linear_text(text, returncode=1)
        if result.get("class") != expected_class:
            raise AssertionError(
                f"{name} classification drift: {result.get('class')} != {expected_class}"
            )
        if result.get("status") == "PASS":
            raise AssertionError(f"negative control unexpectedly passed: {name}")

    low_separation = base.replace(
        "1.0e-12 true resid norm 2.0e-03",
        "1.0e-03 true resid norm 2.0e-03",
        1,
    )
    low = recipe.analyze_first_linear_text(low_separation, returncode=1)
    if low.get("class") != "KSP_BREAKDOWN_WITHOUT_RESIDUAL_FIDELITY_LOSS":
        raise AssertionError("low residual separation was over-classified")


def _check_primitive_usage() -> None:
    source = Path(recipe.__file__).read_text()
    required = (
        "from physics_harness.reasoning import diagnose_coupled_runtime_evidence",
        "from physics_harness.reasoning.jacobian import diagnose_jacobian_evidence",
        "from physics_harness.adapters.moose.nonlinear_solver import runtime_core_facts",
        "from physics_harness.adapters.petsc import ksp",
        "from physics_harness.adapters.petsc import log as petsc_log",
        "from physics_harness.adapters.petsc.log import first_linear_termination",
        "from physics_harness.adapters.moose import petsc_options as po",
        "from physics_harness.adapters.moose.mutation_spec import compile_mutation_spec, load_mutation_json_file",
        "from physics_harness.adapters.moose.transforms import TransformError, apply_case_plan",
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"recipe does not use expected generic primitive: {token}")

    forbidden = (
        "qpx_harness",
        "electron_inventory_nullspace",
        "petsc_first_linear_diagnostic",
        "fast_plasma_coupling_diagnostic",
        "augmented_jacobian_localization",
        "jacobian_fd_reference_audit",
    )
    for token in forbidden:
        if token in source:
            raise AssertionError(f"reverse dependency leaked into Issue45 recipe: {token}")


def main() -> int:
    try:
        _check_construction()
        print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHECK: construction=PASS")
        _check_analysis_positive()
        print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHECK: positive-analysis=PASS")
        _check_analysis_negative_controls()
        print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHECK: negative-controls=PASS")
        _check_primitive_usage()
        print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHECK: recipe-reverse-dependency=NONE")
    except Exception as exc:
        print(f"ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
