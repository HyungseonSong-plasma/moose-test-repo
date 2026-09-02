#!/usr/bin/env python3
"""P0 characterization for final fast_plasma_relaxation_v2 runtime absorption."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import evidence
from qpx_harness import issue43_fast_relaxation as v5
from qpx_harness import issue43_relaxation_runtime as runtime43
from qpx_harness.moose import preflight
from qpx_harness.evidence import artifacts
from qpx_harness.execution import cases, runtime
from qpx_harness import scale_audit
from recipes import issue43_fast_relaxation as recipe

V5 = ROOT / "qpx_harness" / "issue43_fast_relaxation.py"

V5_RETIRED_V2_RUNTIME_TOKENS = (
    "from . import fast_plasma_relaxation_v2 as v2",
    "_RAW_BUILD_ELECTRON_300K = v2._build_electron_300k",
    "_V2_BUILD_ONEWAY = v2._build_oneway",
    "_V2_BUILD_FEEDBACK = v2._build_feedback",
    "_RAW_RUN_CASE = v2._run_case",
    "_RAW_CLASSIFY = v2.classify",
    "v2._attach_residual(",
    "v2._physics_pass(",
    "v2._run_known_good(",
    "v2.self_test()",
    "def _install_v2_repairs(",
    "def _install_v5_repairs(",
)

V5_CANONICAL_RUNTIME_TOKENS = (
    "from . import issue43_relaxation_runtime as issue43_runtime",
    "_RAW_BUILD_ELECTRON_300K = issue43_runtime.build_electron_300k",
    "_RAW_BUILD_ONEWAY = issue43_runtime.build_oneway",
    "_RAW_BUILD_FEEDBACK = issue43_runtime.build_feedback",
    "_RAW_RUN_CASE = issue43_runtime.run_case",
    "_RAW_CLASSIFY = relaxation_recipe.classify",
    "issue43_runtime.run_known_good(",
    "issue43_runtime.physics_pass(",
    "issue43_runtime.attach_nonlinear_residual(",
    "issue43_runtime.self_test()",
)

V5_DIRECT_INFRA_TOKENS = (
    "from .execution import cases as case_ops",
    "from .moose import preflight",
    "from . import scale_audit",
    "from .execution.runtime import resolve_executable, run_qpx, validate_executable",
    "artifacts.write_json_bundle(",
    "evidence.create_collision_safe_directory(",
    "case_ops.stage_case(",
    "case_ops.validate_case_references(",
    "scale_audit.mesh_stats(",
    "scale_audit.anchor_scales(",
    "preflight.validate_parser_symbols_text(",
    "resolve_executable(",
    "validate_executable(",
)

ISSUE43_POLICY_TOKENS = (
    '"KNOWN_GOOD_ELECTRON_CONTROL_FAIL"',
    '"ELECTRON_300K_CONTROL_FAIL"',
    '"POISSON_OR_BLOCK_SCALING_FAIL"',
    '"FEEDBACK_CASE_MISSING"',
    '"FEEDBACK_IMPLICIT_COUPLING_RECOVERS_NEAR_TAU_DR"',
    '"DIELECTRIC_TIMESTEP_STIFFNESS_CONFIRMED"',
    '"FEEDBACK_RECOVERS_BELOW_TAU_DR"',
    '"DIELECTRIC_TIMESTEP_STIFFNESS_STRONG"',
    '"FEEDBACK_JACOBIAN_SCALING_OR_INITIALIZATION_FAIL"',
    '"FEEDBACK_DISCRIMINATOR_INCOMPLETE"',
)


def _text(path: Path) -> str:
    return path.read_text()


def _fixture() -> str:
    return """[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1e16
    block = plasma
  []
[]
[Functions]
  [phi_prescribed]
    type = ParsedFunction
    expression = '-0.01*x'
  []
[]
[FunctorMaterials]
  [electron_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en p_abs T_g carrier_one'
    prop_values = '5.73276 1.33322 600.0 1.0'
    block = plasma
  []
[]
[FVKernels]
  [drift]
    type = QPXFVElectrostaticDrift
    variable = n_e
    potential = phi_prescribed
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    block = plasma
  []
[]
[Postprocessors]
  [n_min]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = min
    block = plasma
  []
[]
[Executioner]
  type = Transient
  dt = 1e-8
  end_time = 2e-8
  compute_scaling_once = true
[]
[Outputs]
  csv = true
[]
"""


def _check_zero_runtime_consumers() -> None:
    tokens = (
        "from . import fast_plasma_relaxation_v2 as v2",
        "import qpx_harness.fast_plasma_relaxation_v2 as v2",
    )
    observed: set[str] = set()
    for path in (ROOT / "qpx_harness").glob("*.py"):
        if path.name == "fast_plasma_relaxation_v2.py":
            continue
        source = _text(path)
        if any(token in source for token in tokens):
            observed.add(path.name)
    if observed:
        raise AssertionError(f"v2 runtime consumers remain: {sorted(observed)}")


def _check_v5_current_surface() -> None:
    source = _text(V5)
    for token in V5_RETIRED_V2_RUNTIME_TOKENS:
        if token in source:
            raise AssertionError(f"v5 retained v2 runtime surface: {token}")
    for token in V5_CANONICAL_RUNTIME_TOKENS:
        if token not in source:
            raise AssertionError(f"v5 canonical runtime absorption drift: {token}")
    for token in V5_DIRECT_INFRA_TOKENS:
        if token not in source:
            raise AssertionError(f"v5 direct generic infrastructure drift: {token}")


def _check_v5_infrastructure_behavior() -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        source = root / "source"
        source.mkdir()
        (source / "asset.dat").write_text("asset\n")
        (source / "input.i").write_text("table_file = asset.dat\n")
        (source / "input_out.csv").write_text("stale\n")
        (source / ".jitcache").mkdir()
        (source / ".jitcache" / "jit.o").write_text("stale\n")

        target = root / "target"
        v5._stage_case(source, target, "table_file = asset.dat\n")
        if (target / "input_out.csv").exists() or (target / ".jitcache").exists():
            raise AssertionError("v5 canonical staging retained stale runtime artifacts")
        expected_asset = str((target / "asset.dat").resolve())
        if v5._validate_assets(target) != [expected_asset]:
            raise AssertionError("v5 canonical asset validation changed path schema")

        (target / "asset.dat").unlink()
        try:
            v5._validate_assets(target)
        except recipe.Issue43FastRelaxationError:
            pass
        else:
            raise AssertionError("v5 canonical asset validation accepted a missing asset")

        summary_path = root / "summary.json"
        payload = {"z": 1, "a": [2, 3]}
        v5._write_json(summary_path, payload)
        if json.loads(summary_path.read_text()) != payload:
            raise AssertionError("v5 canonical JSON writer changed payload semantics")
        if summary_path.read_text().find('"a"') > summary_path.read_text().find('"z"'):
            raise AssertionError("v5 canonical JSON writer lost deterministic key ordering")

        original_timestamp = evidence.utc_timestamp
        evidence.utc_timestamp = lambda: "20260831T140000Z"
        try:
            results = root / "results"
            first = v5._create_root(results)
            second = v5._create_root(results)
        finally:
            evidence.utc_timestamp = original_timestamp

        stem = "fast_plasma_discriminator_v2_Issue43_20260831T140000Z"
        if [first.name, second.name] != [stem, f"{stem}_01"]:
            raise AssertionError("v5 collision-safe run-root contract drift")
        if not first.is_dir() or not second.is_dir():
            raise AssertionError("v5 collision-safe run-root helper did not create directories")


def _check_runtime_absorption_behavior() -> None:
    base = _fixture()
    feedback = runtime43.build_feedback(
        base,
        dt=runtime43.DT_FEEDBACK_BASE,
        steps=runtime43.N_STEPS,
        radial_span=0.243,
    )
    expected_feedback, _ = recipe.build_fast_input(
        base,
        gas_temperature=runtime43.GAS_TEMPERATURE,
        electron_density=scale_audit.DEFAULT_ELECTRON_DENSITY,
        dt=runtime43.DT_FEEDBACK_BASE,
        end_time=runtime43.DT_FEEDBACK_BASE * runtime43.N_STEPS,
        radial_span=0.243,
    )
    if feedback != expected_feedback:
        raise AssertionError("canonical feedback builder drifted from recipe construction")

    oneway = runtime43.build_oneway(
        base,
        dt=runtime43.DT_FEEDBACK_BASE,
        steps=runtime43.N_STEPS,
        radial_span=0.243,
    )
    if "potential = phi_prescribed" not in oneway:
        raise AssertionError("canonical one-way builder lost prescribed potential")

    electron = runtime43.build_electron_300k(
        base,
        dt=runtime43.DT_ELECTRON_CONTROL,
        steps=runtime43.N_STEPS,
    )
    if "potential = phi_prescribed" not in electron or "300" not in electron:
        raise AssertionError("canonical electron control construction drift")

    with tempfile.TemporaryDirectory() as tmp_name:
        log = Path(tmp_name) / "residual.log"
        log.write_text(
            " 0 Nonlinear |R| = 1.0e+03\n"
            " 1 Nonlinear |R| = 1.0e+01\n"
            " 2 Nonlinear |R| = 2.0e+00\n"
        )
        summary = runtime43.nonlinear_residual_summary(str(log))
        if summary is None:
            raise AssertionError("canonical residual parser returned no evidence")
        if summary["initial_residual"] != 1.0e3 or summary["minimum_residual"] != 2.0:
            raise AssertionError("canonical residual summary values drifted")
        if summary["final_solve_residuals"] != [1.0e3, 1.0e1, 2.0]:
            raise AssertionError("canonical residual trajectory drifted")

    if not runtime43.physics_pass({"class": "P3_PASS", "analysis": {"status": "PASS"}}):
        raise AssertionError("canonical physics-pass positive control failed")
    if runtime43.physics_pass({"class": "P3_PASS", "analysis": {"status": "FAIL"}}):
        raise AssertionError("canonical physics-pass rejected-analysis control failed")
    if runtime43.physics_pass({"class": "SOLVER_CONVERGENCE_FAIL"}):
        raise AssertionError("canonical physics-pass solver-failure control failed")

    if runtime43.self_test() != 0:
        raise AssertionError("canonical Issue43 runtime self-test failed")


def _check_destination_readiness() -> None:
    for owner, name in (
        (cases, "stage_case"),
        (cases, "validate_case_references"),
        (runtime, "resolve_executable"),
        (runtime, "validate_executable"),
        (artifacts, "write_json_bundle"),
        (evidence, "create_collision_safe_directory"),
        (scale_audit, "mesh_stats"),
        (scale_audit, "anchor_scales"),
        (preflight, "validate_parser_symbols_text"),
        (runtime43, "build_electron_300k"),
        (runtime43, "build_oneway"),
        (runtime43, "build_feedback"),
        (runtime43, "run_case"),
        (runtime43, "run_known_good"),
        (runtime43, "attach_nonlinear_residual"),
        (runtime43, "physics_pass"),
        (recipe, "find_relaxation_csv"),
        (recipe, "build_fast_input"),
        (recipe, "classify"),
    ):
        if not callable(getattr(owner, name, None)):
            raise AssertionError(f"canonical destination missing: {owner.__name__}.{name}")


def _check_scientific_policy_boundary() -> None:
    recipe_source = _text(Path(recipe.__file__))
    runtime_source = _text(Path(runtime43.__file__))

    if "def classify(" not in recipe_source:
        raise AssertionError("recipe does not own Issue43 scientific classification")
    for token in ISSUE43_POLICY_TOKENS:
        if token not in recipe_source:
            raise AssertionError(f"recipe Issue43 policy class drift: {token}")
    if "def classify(" in runtime_source:
        raise AssertionError("runtime duplicated scientific classification policy")
    if v5._RAW_CLASSIFY is not recipe.classify:
        raise AssertionError("v5 classification is not directly bound to canonical recipe")

    for forbidden in (
        "fast_plasma_relaxation_v2",
        "fast_plasma_relaxation_v5",
        "qpx_harness.runtime",
        "qpx_harness.cases",
    ):
        if forbidden in recipe_source:
            raise AssertionError(f"recipe reverse dependency leaked: {forbidden}")
    for forbidden in (
        "fast_plasma_relaxation_v2",
        "fast_plasma_relaxation_v5",
    ):
        if forbidden in runtime_source:
            raise AssertionError(f"runtime version dependency leaked: {forbidden}")


def main() -> int:
    try:
        _check_zero_runtime_consumers()
        _check_v5_current_surface()
        _check_v5_infrastructure_behavior()
        _check_runtime_absorption_behavior()
        _check_destination_readiness()
        _check_scientific_policy_boundary()
    except Exception as exc:
        print(f"ISSUE48_V5_V2_ABSORPTION_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_V5_V2_ABSORPTION_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
