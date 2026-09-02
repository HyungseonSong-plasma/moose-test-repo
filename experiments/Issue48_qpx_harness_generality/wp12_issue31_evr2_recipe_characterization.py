#!/usr/bin/env python3
"""P0 characterization for Issue31 EVR2 recipe-backed production cutover."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recipes import issue31_coupling as recipe
from qpx_harness.coupling_evr2 import orchestration as production


EXPECTED_EVR1_BASELINE = {
    "dt": 1.0e-4,
    "status": "RUNTIME_FAIL_OR_NONCONVERGENCE",
    "signature": "DIVERGED_MAX_IT",
    "nonlinear_iterations": 80,
    "physics": "NOT_RUN",
    "source": "user-returned Issue31 EVR1 transport-only evidence",
}
EXPECTED_TERMINAL_CLASSES = {
    "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_BY_1E6",
    "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_ONLY_BY_1E8",
    "NONLINEAR_SCALING_SENSITIVITY_CONFIRMED",
    "T3_COUPLING_OR_JACOBIAN_FAIL_PERSISTS",
    "NONMONOTONIC_TIMESTEP_RESPONSE",
}


def _synthetic_input() -> str:
    return """
[Variables]
  [n_e_solved]
  []
  [potential_plasma]
  []
[]
[FunctorMaterials]
  [r30_charge_density]
  []
[]
[FVKernels]
  [r30_e_time]
  []
  [r30_e_diffusion]
  []
  [r30_phi_diffusion]
  []
  [r30_phi_charge_source]
  []
[]
[FVBCs]
  [r30_phi_plasma_metal]
  []
  [r30_phi_plasma_electrode]
  []
  [r30_phi_plasma_right]
  []
  [r30_phi_inlet]
  []
  [r30_phi_outlet]
  []
[]
[Postprocessors]
  [r29_phi_min]
  []
  [r29_phi_max]
  []
  [r29_phi_integral]
  []
[]
[Executioner]
  type = Transient
  dt = 1.0e-4
  end_time = 5.0e-4
  compute_scaling_once = false
[]
"""


def _case(
    status: str,
    *,
    physics: str | None = None,
    signature: str | None = None,
    checker: str | None = None,
) -> dict:
    value = {
        "result": {"validation": {"status": status}},
        "failure": {"signature": signature},
    }
    if physics is not None:
        value["physics"] = {"status": physics}
    if checker is not None:
        value["canonical_checker"] = {"status": checker}
    return value


def _check_constants() -> None:
    expected = (
        (recipe.KG_E_PARENT_RELATIVE, Path("tests/Issue2_electron_bulk_drift")),
        (recipe.EVR1_BASELINE, EXPECTED_EVR1_BASELINE),
        (recipe.DT_1E6, 1.0e-6),
        (recipe.DT_1E8, 1.0e-8),
        (recipe.EVR2_TERMINAL_CLASSES, EXPECTED_TERMINAL_CLASSES),
    )
    for actual, wanted in expected:
        if actual != wanted:
            raise AssertionError(f"EVR2 recipe constant drift: {actual!r} != {wanted!r}")


def _check_transform_contract() -> None:
    base = _synthetic_input()
    for dt, scaling in (
        (recipe.DT_1E6, False),
        (recipe.DT_1E8, False),
        (recipe.DT_1E8, True),
    ):
        text, meta = recipe.configured_transport_input(
            base,
            dt=dt,
            compute_scaling_once=scaling,
        )
        if "potential_plasma" in text:
            raise AssertionError("EVR2 recipe left Poisson state in transport control")
        if "n_e_solved" not in text or "r30_e_diffusion" not in text:
            raise AssertionError("EVR2 recipe lost solved-electron transport state")
        if meta["dt"] != dt or meta["compute_scaling_once"] is not scaling:
            raise AssertionError("EVR2 recipe timestep/scaling metadata drift")
        params = meta["executioner_parameters"]
        if params["dt"]["old"] != "1.0e-4":
            raise AssertionError("EVR2 recipe dt old-value metadata drift")
        if params["end_time"]["old"] != "5.0e-4":
            raise AssertionError("EVR2 recipe end_time old-value metadata drift")
        expected_scaling = "true" if scaling else "false"
        if params["compute_scaling_once"]["new"] != expected_scaling:
            raise AssertionError("EVR2 recipe scaling new-value metadata drift")

    bad = base.replace("[Executioner]\n", "[NotExecutioner]\n")
    try:
        recipe.configured_transport_input(
            bad,
            dt=recipe.DT_1E8,
            compute_scaling_once=False,
        )
    except recipe.Issue31CouplingError:
        pass
    else:
        raise AssertionError("EVR2 missing-Executioner negative control passed")


def _assert_decision(expected: dict, *scenario) -> None:
    actual = recipe.classify_evr2(*scenario)
    if actual != expected:
        raise AssertionError(f"EVR2 classification contract drift: {actual} != {expected}")


def _check_classification_contract() -> None:
    kg = _case("P2_PASS_P3_PASS", physics="PASS", checker="PASS")
    kg_runtime_fail = _case(
        "RUNTIME_FAIL_OR_NONCONVERGENCE",
        signature="DIVERGED_MAX_IT",
    )
    kg_construction_fail = _case("HARNESS_OR_CONSTRUCTION_FAIL")
    passed = _case("P2_PASS_P3_PASS", physics="PASS")
    physics_fail = _case("P2_PASS_P3_PASS", physics="FAIL")
    construction_fail = _case("HARNESS_OR_CONSTRUCTION_FAIL")
    nonlinear_fail = _case(
        "RUNTIME_FAIL_OR_NONCONVERGENCE",
        signature="DIVERGED_MAX_IT",
    )
    runtime_other = _case("RUNTIME_FAIL_OR_NONCONVERGENCE", signature=None)

    _assert_decision(
        {
            "class": "KNOWN_GOOD_ELECTRON_CONTROL_FAIL",
            "reason": "accepted real-qvt electron control did not pass on the current executable/environment",
        },
        kg_runtime_fail,
        None,
        None,
        None,
    )
    _assert_decision(
        {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "accepted real-qvt electron control did not pass on the current executable/environment",
        },
        kg_construction_fail,
        None,
        None,
        None,
    )
    _assert_decision(
        {"class": "HARNESS_OR_CONSTRUCTION_FAIL", "reason": "dt1e6 was not run"},
        kg,
        None,
        passed,
        None,
    )
    _assert_decision(
        {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "dt1e6 failed before interpretable physics runtime",
        },
        kg,
        construction_fail,
        passed,
        None,
    )
    _assert_decision(
        {
            "class": "PHYSICS_CHECK_FAIL",
            "reason": "dt1e6 runtime completed but transport physics checks failed",
        },
        kg,
        physics_fail,
        passed,
        None,
    )
    _assert_decision(
        {
            "class": "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_BY_1E6",
            "reason": "EVR1 dt=1e-4 failed; unchanged transport/scaling recovers at both 1e-6 and 1e-8",
        },
        kg,
        passed,
        passed,
        None,
    )
    _assert_decision(
        {
            "class": "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_ONLY_BY_1E8",
            "reason": "dt=1e-6 still fails by nonlinear convergence while dt=1e-8 recovers with unchanged scaling",
        },
        kg,
        nonlinear_fail,
        passed,
        None,
    )
    _assert_decision(
        {
            "class": "NONMONOTONIC_TIMESTEP_RESPONSE",
            "reason": "dt=1e-6 passes but smaller dt=1e-8 does not; simple timestep-stiffness explanation is insufficient",
        },
        kg,
        passed,
        nonlinear_fail,
        None,
    )
    _assert_decision(
        {
            "class": "SCALING_BRANCH_REQUIRED",
            "reason": "both smaller timesteps remain nonlinear-convergence failures",
        },
        kg,
        nonlinear_fail,
        nonlinear_fail,
        None,
    )
    _assert_decision(
        {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "scaling discriminator failed before interpretable physics runtime",
        },
        kg,
        nonlinear_fail,
        nonlinear_fail,
        construction_fail,
    )
    _assert_decision(
        {
            "class": "PHYSICS_CHECK_FAIL",
            "reason": "scaling discriminator converged but physics checks failed",
        },
        kg,
        nonlinear_fail,
        nonlinear_fail,
        physics_fail,
    )
    _assert_decision(
        {
            "class": "NONLINEAR_SCALING_SENSITIVITY_CONFIRMED",
            "reason": "dt=1e-8 fails with current scaling policy and recovers when only compute_scaling_once changes to true",
        },
        kg,
        nonlinear_fail,
        nonlinear_fail,
        passed,
    )
    _assert_decision(
        {
            "class": "T3_COUPLING_OR_JACOBIAN_FAIL_PERSISTS",
            "reason": "accepted electron control passes, but T3 fails at 1e-6 and 1e-8 and does not recover with accepted scaling-once policy",
        },
        kg,
        nonlinear_fail,
        nonlinear_fail,
        nonlinear_fail,
    )
    _assert_decision(
        {
            "class": "UNRESOLVED_RUNTIME_RESPONSE",
            "reason": "observed result signature does not match a predeclared discriminator branch",
        },
        kg,
        runtime_other,
        runtime_other,
        None,
    )


def _imports_module(path: Path, module: str) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == module for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if base == module:
                return True
            if base == "qpx_harness" and module.startswith("qpx_harness."):
                leaf = module.split(".", 1)[1]
                if any(alias.name == leaf for alias in node.names):
                    return True
    return False


def _check_recipe_boundary() -> None:
    path = Path(recipe.__file__)
    source = path.read_text()
    for forbidden in (
        "coupling_evr2_timestep",
        "run_measurement",
        "resolve_executable",
        "validate_executable",
        "subprocess.run",
        "shutil.copytree",
        "hashlib.sha256",
        "normalize_from_manifest",
        "default_results_root",
    ):
        if forbidden in source:
            raise AssertionError(f"Issue31 recipe leaked EVR2 runtime mechanics: {forbidden}")
    if _imports_module(path, "qpx_harness.coupling_evr2_timestep"):
        raise AssertionError("Issue31 recipe reverse-imports EVR2 runtime owner")


def _check_production_cutover() -> None:
    this_path = Path(__file__)
    if _imports_module(this_path, "qpx_harness.coupling_evr2_timestep"):
        raise AssertionError("WP12 retained legacy EVR2 oracle import")

    source = Path(production.__file__).read_text()
    for required in (
        "recipe.configured_transport_input(",
        "recipe.classify_evr2(",
        "recipe.KG_E_PARENT_RELATIVE",
        "recipe.EVR1_BASELINE",
        "recipe.DT_1E6",
        "recipe.DT_1E8",
        "recipe.EVR2_TERMINAL_CLASSES",
    ):
        if required not in source:
            raise AssertionError(f"EVR2 production recipe cutover missing: {required}")
    for forbidden in (
        "def configured_transport_input(",
        "def classify(",
        "KG_E_PARENT_RELATIVE =",
        "EVR1_BASELINE =",
        "DT_1E6 =",
        "DT_1E8 =",
        "from .moose.input import",
        "coupling_evr2_timestep",
    ):
        if forbidden in source:
            raise AssertionError(f"EVR2 production retained scientific/legacy duplicate: {forbidden}")
    for runtime_token in (
        "run_measurement",
        "subprocess.run",
        "stage_case",
        "write_json_bundle",
        "sha256_file",
        "resolve_executable",
        "validate_executable",
    ):
        if runtime_token not in source:
            raise AssertionError(f"EVR2 canonical runtime ownership missing: {runtime_token}")


def main() -> int:
    try:
        _check_constants()
        _check_transform_contract()
        _check_classification_contract()
        _check_recipe_boundary()
        _check_production_cutover()
        if production.self_test() != 0:
            raise AssertionError("EVR2 canonical runtime self-test failed after recipe cutover")
    except Exception as exc:
        print(f"ISSUE48_ISSUE31_EVR2_RECIPE_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE31_EVR2_RECIPE_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
