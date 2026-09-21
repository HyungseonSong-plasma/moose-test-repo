#!/usr/bin/env python3
"""P0 characterization for the historical Issue46 FD-reference recipe."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.historical_recipe_support import issue45_first_linear as issue45_recipe
from experiments.historical_recipe_support import issue46_fd_reference as recipe
from experiments.historical_recipe_support import issue46_jacobian_localization as localization_recipe


SQRT_MACHINE_EPSILON = math.sqrt(sys.float_info.epsilon)


def _synthetic_constrained_input(macro_avg: float = recipe.TARGET) -> str:
    """Frozen pre-retirement Issue46 constrained C0 fixture."""
    return f"""[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = {recipe.TARGET:.17g}
  []
  [potential_plasma]
    type = MooseVariableFVReal
  []
  [{recipe.LAMBDA_VARIABLE}]
    type = MooseVariableScalar
  []
[]
[FVKernels]
  [diffusion]
    type = FVDiffusion
    variable = n_e
  []
  [drift]
    type = QPXFVElectrostaticDrift
    variable = n_e
    boundaries_to_avoid = 'inlet outlet plasma_cover plasma_electrode plasma_focus_ring plasma_metal plasma_right plasma_wafer'
  []
  [phi]
    type = FVDiffusion
    variable = potential_plasma
  []
  [inventory_constraint]
    type = FVIntegralValueConstraint
    variable = n_e
    lambda = {recipe.LAMBDA_VARIABLE}
    phi0 = r45_ne_macro_avg
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
  [r45_ne_macro_avg]
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


def _baseline_text() -> str:
    first_text, _ = issue45_recipe.instrument_first_linear(
        _synthetic_constrained_input(recipe.TARGET)
    )
    baseline, _ = localization_recipe.instrument_localization(first_text)
    return baseline


def _synthetic_dofmap() -> str:
    return json.dumps(
        {
            "ndof": 5,
            "vars": [
                {"name": "n_e", "subdomains": [{"id": 1, "dofs": [0, 1]}]},
                {
                    "name": "potential_plasma",
                    "subdomains": [{"id": 1, "dofs": [2, 3]}],
                },
                {
                    "name": recipe.LAMBDA_VARIABLE,
                    "subdomains": [{"id": 1, "dofs": []}],
                },
            ],
        }
    )


def _synthetic_log(relative_error: float, rows: list[str]) -> str:
    return (
        "  ---------- Testing Jacobian -------------\n"
        f"  ||J - Jfd||_F/||J||_F = {relative_error:.12e}, "
        "||J - Jfd||_F = 1e-6\n"
        f"  Hand-coded minus finite-difference Jacobian with tolerance "
        f"{recipe.LOCALIZATION_THRESHOLD:.12e} ----------\n"
        "Mat Object: 1 MPI process\n  type: seqaij\n"
        + "\n".join(rows)
        + "\nLinear solve did not converge due to DIVERGED_BREAKDOWN iterations 30\n"
    )


def _check_predictor_and_construction() -> None:
    explicit = recipe.predict_fd_step_quantization(
        vector_norm=123.0,
        component_value=7.0,
    )
    if explicit["wp_requested_dx"] != math.sqrt(124.0) * SQRT_MACHINE_EPSILON:
        raise AssertionError("WP predictor ignored explicit vector norm")
    if explicit["ds_requested_dx"] != 7.0 * SQRT_MACHINE_EPSILON:
        raise AssertionError("DS predictor ignored explicit component value")

    prediction = recipe.historical_evr1_prediction()
    if prediction["electron_dofs"] != 2348.0 or prediction["electron_value"] != 1.0e16:
        raise AssertionError("historical EVR1 predictor identity drift")
    if abs(prediction["ds_predicted_attenuation"] - 1.0) > recipe.DS_ATTENUATION_TO_UNITY_TOL:
        raise AssertionError("historical DS perturbation representability drift")

    mechanism = recipe.historical_mechanism_evidence()
    if (
        mechanism.get("status") != "PASS"
        or mechanism.get("class") != "WP_QUANTIZATION_MECHANISM_CHARACTERIZED"
        or mechanism.get("reference_source", {}).get("version") != "3.25.2"
    ):
        raise AssertionError("historical WP mechanism evidence drift")

    baseline = _baseline_text()
    ds_text, meta = recipe.instrument_ds_reference(baseline)
    if meta != {
        "mat_fd_type": "ds",
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "scaling_policy_changed": False,
        "finite_difference_observation_changed": True,
    }:
        raise AssertionError(f"DS construction metadata drift: {meta}")
    if "-mat_fd_type" not in ds_text or " ds" not in ds_text:
        raise AssertionError("DS finite-difference option was not inserted")
    restored = recipe.remove_fd_type_pair(ds_text)
    if recipe.mask_petsc_pair_lines(restored) != recipe.mask_petsc_pair_lines(baseline):
        raise AssertionError("DS observation-only restoration contract drift")


def _check_directional_localization() -> None:
    result = recipe.directional_localization(
        _synthetic_log(
            4.0e-5,
            ["row 0: (4, 0.0)", "row 4: (0, 2.0e-4)"],
        ),
        _synthetic_dofmap(),
    )
    metrics = result["metrics"]
    if metrics["structural_entry_count"] != 2:
        raise AssertionError("directional structural entry count drift")
    if metrics["nonzero_thresholded_entry_count"] != 1:
        raise AssertionError("directional nonzero threshold count drift")
    if metrics["j_lambda_n"]["count"] != 1:
        raise AssertionError("J_lambda,n direction was not identified")
    if metrics["j_n_lambda"]["count"] != 0:
        raise AssertionError("zero J_n,lambda entry was misclassified")


def _check_termination_and_applicability() -> None:
    cases = (
        (_synthetic_log(5.0e-11, []), 1, "PASS", "EXPECTED_DIAGNOSTIC_NONCONVERGENCE"),
        (
            _synthetic_log(5.0e-11, []) + "Segmentation fault (core dumped)\n",
            139,
            "HOLD",
            "FATAL_RUNTIME_FAILURE",
        ),
        ("runtime completed\n", 0, "PASS", "TERMINATION_SUCCESS"),
        ("runtime failed\n", 2, "HOLD", "TERMINATION_AMBIGUOUS"),
    )
    for text, rc, status, klass in cases:
        result = recipe.termination_admissibility(text, returncode=rc)
        if result.get("status") != status or result.get("class") != klass:
            raise AssertionError(f"termination contract drift: {result}")

    applicability_cases = (
        (
            "PETSc Release Version 3.25.2\n",
            "PASS",
            "PETSC_WP_MECHANISM_APPLICABILITY_PASS",
            "3.25.2",
        ),
        (
            "PETSC_VERSION=3.24.0\n",
            "HOLD",
            "PETSC_WP_MECHANISM_APPLICABILITY_DRIFT",
            "3.24.0",
        ),
        (
            "no version here\n",
            "HOLD",
            "PETSC_WP_MECHANISM_APPLICABILITY_UNRESOLVED",
            "UNKNOWN",
        ),
    )
    for text, status, klass, version in applicability_cases:
        result = recipe.runtime_mechanism_applicability(text)
        if (
            result.get("status") != status
            or result.get("class") != klass
            or result.get("runtime_version") != version
        ):
            raise AssertionError(f"runtime applicability contract drift: {result}")


def _provenance_kwargs(*, log_preexisting: bool = False, input_after: str = "abc"):
    root = Path("/tmp/issue46-evidence")
    case = root / "c0_ds_reference"
    return {
        "root": root,
        "case_dir": case,
        "input_path": case / "input.i",
        "source_case": Path("/tmp/issue46-source-case"),
        "input_sha_before": "abc",
        "input_sha_after": input_after,
        "log_path": root / "p3_c0_ds_reference.log",
        "log_preexisting": log_preexisting,
        "log_exists": True,
        "dofmap_path": case / "r46_dofmap.json",
        "dofmap_preexisting": False,
        "dofmap_exists": True,
        "source_dofmaps_before": (),
        "source_dofmaps_after": (),
    }


def _check_provenance() -> None:
    positive = recipe.evidence_provenance_status(**_provenance_kwargs())
    if positive.get("status") != "PASS" or positive.get("class") != "EVIDENCE_PROVENANCE_PASS":
        raise AssertionError(f"fresh provenance contract drift: {positive}")

    stale = recipe.evidence_provenance_status(**_provenance_kwargs(log_preexisting=True))
    if stale.get("status") != "HOLD" or "current-run-log" not in stale.get("blockers", []):
        raise AssertionError(f"stale-log provenance contract drift: {stale}")

    drift = recipe.evidence_provenance_status(**_provenance_kwargs(input_after="drift"))
    if drift.get("status") != "HOLD" or "input-identity-stable" not in drift.get("blockers", []):
        raise AssertionError(f"input-drift provenance contract drift: {drift}")


def _check_final_discriminator() -> None:
    identity = {
        "status": "PASS",
        "class": "ISSUE46_EXPERIMENT_IDENTITY_PASS",
        "reason": "characterized identity",
    }
    applicability = {
        "status": "PASS",
        "class": "PETSC_WP_MECHANISM_APPLICABILITY_PASS",
        "reason": "characterized applicability",
        "reference_version": "3.25.2",
        "runtime_version": "3.25.2",
    }
    dofmap = _synthetic_dofmap()
    cases = (
        (
            _synthetic_log(5.0e-11, []),
            "PASS",
            "FD_REFERENCE_QUANTIZATION_CONFIRMED",
            "DS_REFERENCE_JACOBIAN_PASS",
        ),
        (
            _synthetic_log(4.0e-5, ["row 4: (0, 2.0e-4)"]),
            "HOLD",
            "FD_REFERENCE_MISMATCH_PERSISTS",
            "FD_REFERENCE_MISMATCH_PERSISTS",
        ),
        (
            _synthetic_log(5.0e-11, []).split("Linear solve", 1)[0],
            "HOLD",
            "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
            "FD_REFERENCE_DISCRIMINATOR_INSUFFICIENT",
        ),
    )
    for log, status, klass, ds_class in cases:
        result = recipe.analyze_ds_runtime(
            log,
            dofmap,
            returncode=1,
            experiment_identity=identity,
            mechanism_applicability=applicability,
        )
        if result.get("status") != status or result.get("class") != klass:
            raise AssertionError(f"final discriminator contract drift: {result}")
        if result.get("ds_discriminator", {}).get("class") != ds_class:
            raise AssertionError(f"DS discriminator branch drift: {result}")


def _check_dependency_boundary() -> None:
    source = Path(recipe.__file__).read_text()
    forbidden = (
        "qpx_harness",
        "augmented_jacobian_localization",
        "electron_inventory_nullspace",
        "jacobian_fd_reference_audit",
        "petsc_first_linear_diagnostic",
        "fast_plasma_coupling_diagnostic",
    )
    for token in forbidden:
        if token in source:
            raise AssertionError(f"legacy reverse dependency leaked into Issue46 recipe: {token}")
    required = (
        "from physics_harness.evidence import artifacts",
        "from physics_harness.adapters.moose import dofmap as dm",
        "from physics_harness.adapters.petsc import fd_reference as fd",
        "from physics_harness.adapters.petsc import matrix as matrix",
        "from physics_harness.adapters.moose import petsc_options as options",
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"Issue46 recipe does not compose required generic layer: {token}")

    for relative in (
        "qpx_harness/issue46_fd_reference.py",
        "physics_harness/issue46_fd_reference.py",
    ):
        if (ROOT / relative).exists():
            raise AssertionError(f"retired Issue46 facade resurrected: {relative}")


def main() -> int:
    try:
        _check_predictor_and_construction()
        print("ISSUE48_WP4_ISSUE46_FD_CHECK: predictor-and-construction=PASS")
        _check_directional_localization()
        print("ISSUE48_WP4_ISSUE46_FD_CHECK: directional-localization=PASS")
        _check_termination_and_applicability()
        print("ISSUE48_WP4_ISSUE46_FD_CHECK: termination-and-applicability=PASS")
        _check_provenance()
        print("ISSUE48_WP4_ISSUE46_FD_CHECK: evidence-provenance=PASS")
        _check_final_discriminator()
        print("ISSUE48_WP4_ISSUE46_FD_CHECK: final-discriminator=PASS")
        _check_dependency_boundary()
        print("ISSUE48_WP4_ISSUE46_FD_CHECK: recipe-reverse-dependency=NONE")
    except Exception as exc:
        print(f"ISSUE48_WP4_ISSUE46_FD_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP4_ISSUE46_FD_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
