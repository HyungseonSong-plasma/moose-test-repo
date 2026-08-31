#!/usr/bin/env python3
"""P0 characterization for Issue31 EVR2 scientific recipe extraction."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recipes import issue31_coupling as recipe
from qpx_harness import coupling_evr2_timestep as legacy


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
    pairs = (
        (recipe.KG_E_PARENT_RELATIVE, legacy.KG_E_PARENT_RELATIVE, Path("tests/Issue2_electron_bulk_drift")),
        (recipe.EVR1_BASELINE, legacy.EVR1_BASELINE, EXPECTED_EVR1_BASELINE),
        (recipe.DT_1E6, legacy.DT_1E6, 1.0e-6),
        (recipe.DT_1E8, legacy.DT_1E8, 1.0e-8),
    )
    for actual, old, expected in pairs:
        if actual != old or actual != expected:
            raise AssertionError(f"EVR2 recipe constant drift: {actual!r} != {old!r} != {expected!r}")
    if recipe.EVR2_TERMINAL_CLASSES != EXPECTED_TERMINAL_CLASSES:
        raise AssertionError("EVR2 terminal-class contract drift")


def _check_transform_equivalence() -> None:
    base = _synthetic_input()
    for dt, scaling in (
        (recipe.DT_1E6, False),
        (recipe.DT_1E8, False),
        (recipe.DT_1E8, True),
    ):
        expected_text, expected_meta = legacy.configured_transport_input(
            base,
            dt=dt,
            compute_scaling_once=scaling,
        )
        actual_text, actual_meta = recipe.configured_transport_input(
            base,
            dt=dt,
            compute_scaling_once=scaling,
        )
        if actual_text != expected_text or actual_meta != expected_meta:
            raise AssertionError(
                f"EVR2 configured transport equivalence drift dt={dt} scaling={scaling}"
            )

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


def _assert_classification_equivalent(
    kg_e: dict,
    dt1e6: dict | None,
    dt1e8: dict | None,
    scaling1e8: dict | None,
) -> None:
    expected = legacy.classify(kg_e, dt1e6, dt1e8, scaling1e8)
    actual = recipe.classify_evr2(kg_e, dt1e6, dt1e8, scaling1e8)
    if actual != expected:
        raise AssertionError(f"EVR2 classification equivalence drift: {actual} != {expected}")


def _check_classification_equivalence() -> None:
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

    scenarios = (
        (kg_runtime_fail, None, None, None),
        (kg_construction_fail, None, None, None),
        (kg, None, passed, None),
        (kg, construction_fail, passed, None),
        (kg, physics_fail, passed, None),
        (kg, passed, passed, None),
        (kg, nonlinear_fail, passed, None),
        (kg, passed, nonlinear_fail, None),
        (kg, nonlinear_fail, nonlinear_fail, None),
        (kg, nonlinear_fail, nonlinear_fail, construction_fail),
        (kg, nonlinear_fail, nonlinear_fail, physics_fail),
        (kg, nonlinear_fail, nonlinear_fail, passed),
        (kg, nonlinear_fail, nonlinear_fail, nonlinear_fail),
        (kg, runtime_other, runtime_other, None),
    )
    for scenario in scenarios:
        _assert_classification_equivalent(*scenario)


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


def _check_boundary() -> None:
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


def main() -> int:
    try:
        _check_constants()
        _check_transform_equivalence()
        _check_classification_equivalence()
        _check_boundary()
    except Exception as exc:
        print(f"ISSUE48_ISSUE31_EVR2_RECIPE_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE31_EVR2_RECIPE_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
