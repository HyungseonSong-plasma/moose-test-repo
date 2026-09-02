from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recipes import issue43_coupling_diagnostic as recipe
from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp
from qpx_harness.moose.input import MooseInput
from qpx_harness.petsc import options as po
from qpx_harness.spec import compile_spec, load_json_file, load_payload
from qpx_harness.transforms import SUPPORTED_OPERATIONS, apply_case_plan

SPEC_PATH = ROOT / "specs" / "experiments" / "issue43_coupling_diagnostic.json"
READINESS_PATH = ROOT / "docs" / "development" / "2026-09-01_issue63_recipe_readiness.json"
CENSUS_MODULE_PATH = ROOT / "tests" / "Issue59_recipe_census" / "inventory.py"
ISSUE60_61_GUARD = ROOT / "tests" / "Issue60_61_experiment_spec" / "final_guard.py"
QPX_CLI = ROOT / "scripts" / "qpx.py"

LEGACY_DIAGNOSTIC_FLAGS = (
    "-snes_converged_reason",
    "-ksp_converged_reason",
    "-snes_monitor",
    "-ksp_monitor",
)
LEGACY_JACOBIAN_FLAGS = ("-snes_test_jacobian",)

COMPATIBILITY_BLOB_BASELINES = {
    "scripts/qpx.py": "b48c6ad0427ad1fe8cfdb7a3b0e54ff4335fb45f",
    "qpx_harness/issue43_coupling_diagnostic.py": "8731b6047d5f5ea6d4ef3bde8a03704c19fc6621",
    "qpx_harness/issue43_coupling/structure.py": "674e4fee960319e45f4f373325071ac42d4e3844",
    "qpx_harness/issue43_coupling/characterization.py": "7b6dd612bbec8d846cd1d9c5a88b856d9af8e7af",
}

EXPECTED_REMAINING_RECIPES = {
    "recipes/issue31_coupling.py",
    "recipes/issue43_fast_relaxation.py",
    "recipes/issue45_first_linear.py",
    "recipes/issue45_inventory_constraint.py",
    "recipes/issue46_fd_reference.py",
    "recipes/issue46_jacobian_localization.py",
}

TERMINAL_CLASSES = {
    "SPEC_READY",
    "PARTIAL_SPEC_PLUS_ALGORITHM",
    "KEEP_PYTHON_ALGORITHM",
    "BLOCKED_BY_MISSING_CAPABILITY",
}

REQUIRED_READINESS_FIELDS = {
    "terminal_classification",
    "current_declarative_data_share",
    "python_responsibilities",
    "missing_capabilities",
    "follow_up_group",
    "follow_up_boundary",
    "compatibility_surface",
    "scientific_runtime_sensitivity",
    "v1_without_extension",
}


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def _legacy_ensure_debug_block(text: str) -> str:
    matches = MooseInput(text).find("Debug")
    if len(matches) > 1:
        raise mb.MooseBlockError("multiple top-level [Debug] blocks")
    if not matches:
        return mb.append_top_level_block(
            text,
            "[Debug]\n  show_var_residual_norms = true\n[]",
        )
    return mp.upsert_parameter(text, "Debug", "show_var_residual_norms", "true")


def legacy_instrument_input(
    input_text: str,
    *,
    jacobian_test: bool = False,
) -> tuple[str, dict[str, Any]]:
    text = _legacy_ensure_debug_block(input_text)
    text = mp.upsert_parameter(text, "Executioner", "verbose", "true")
    required = LEGACY_DIAGNOSTIC_FLAGS + (LEGACY_JACOBIAN_FLAGS if jacobian_test else ())
    text = po.add_flags(text, required)
    text = mp.upsert_parameter(text, "Outputs/console", "all_variable_norms", "true")
    return text, {
        "debug_show_var_residual_norms": True,
        "executioner_verbose": True,
        "console_all_variable_norms": True,
        "petsc_options_added": list(required),
        "jacobian_test": jacobian_test,
        "physics_or_numerics_changed": False,
    }


def base_inputs() -> dict[str, str]:
    base = """[Executioner]\n  type = Transient\n  dt = 1e-14\n  end_time = 1e-14\n  petsc_options_iname = '-pc_type'\n  petsc_options_value = 'lu'\n[]\n[Outputs]\n  [console]\n    type = Console\n  []\n[]\n"""
    existing_debug = base + """[Debug]\n  show_var_residual_norms = false\n[]\n"""
    existing_flags = base.replace(
        "  petsc_options_iname = '-pc_type'\n",
        "  petsc_options = '-snes_view'\n  petsc_options_iname = '-pc_type'\n",
    )
    return {
        "base": base,
        "existing_debug": existing_debug,
        "existing_flags": existing_flags,
    }


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expected_recipe_class(census: ModuleType, recipe_path: str) -> tuple[str, Counter[str], list[str]]:
    symbols = census.top_level_symbols(ROOT / recipe_path)
    profile: Counter[str] = Counter()
    readiness: list[str] = []
    for kind, name in symbols:
        responsibility = census.classify_symbol(recipe_path, kind, name)
        profile[responsibility] += 1
        if responsibility == "DECLARATIVE_TRANSFORM":
            readiness.append(
                census.spec_v1_readiness(recipe_path, kind, name, responsibility)
            )

    has_non_declarative_python = any(
        profile[key] > 0 for key in ("ALGORITHM", "RUNTIME", "CHARACTERIZATION")
    )
    has_transform = profile["DECLARATIVE_TRANSFORM"] > 0
    any_missing_transform = any(value in {"PARTIAL", "NO"} for value in readiness)
    all_transforms_yes = bool(readiness) and all(value == "YES" for value in readiness)

    if any_missing_transform:
        terminal = "BLOCKED_BY_MISSING_CAPABILITY"
    elif has_transform and all_transforms_yes and has_non_declarative_python:
        terminal = "PARTIAL_SPEC_PLUS_ALGORITHM"
    elif has_transform and all_transforms_yes and not has_non_declarative_python:
        terminal = "SPEC_READY"
    elif has_non_declarative_python and not has_transform:
        terminal = "KEEP_PYTHON_ALGORITHM"
    else:
        terminal = "SPEC_READY"
    return terminal, profile, readiness


def run_subprocess(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    failures: list[str] = []

    # Issue62: validate JSON ownership and prove legacy-equivalent rendering.
    try:
        spec = load_json_file(SPEC_PATH)
        plan = compile_spec(spec)
        assert spec.schema_version == 1
        assert spec.experiment_id == "issue43-coupling-diagnostic"
        assert {case.case_id for case in plan.cases} == {"default", "jacobian"}
    except Exception as exc:
        failures.append(f"Issue62 spec validation: {exc}")
        print(f"ISSUE62_SPEC_VALIDATION: FAIL ({exc})")
        plan = None
    else:
        print("ISSUE62_SPEC_VALIDATION: PASS")

    if plan is not None:
        try:
            expected_flags = {
                "default": LEGACY_DIAGNOSTIC_FLAGS,
                "jacobian": LEGACY_DIAGNOSTIC_FLAGS + LEGACY_JACOBIAN_FLAGS,
            }
            assert recipe.DIAGNOSTIC_PETSC_OPTIONS == LEGACY_DIAGNOSTIC_FLAGS
            assert recipe.JACOBIAN_PETSC_OPTIONS == LEGACY_JACOBIAN_FLAGS
            for label, source in base_inputs().items():
                for jacobian_test, case_id in ((False, "default"), (True, "jacobian")):
                    legacy_text, legacy_meta = legacy_instrument_input(
                        source,
                        jacobian_test=jacobian_test,
                    )
                    adapter_text, adapter_meta = recipe.instrument_input(
                        source,
                        jacobian_test=jacobian_test,
                    )
                    direct_text = apply_case_plan(source, plan.case(case_id))
                    if adapter_text != legacy_text:
                        raise AssertionError(f"adapter byte drift: {label}/{case_id}")
                    if direct_text != legacy_text:
                        raise AssertionError(f"direct spec byte drift: {label}/{case_id}")
                    if adapter_meta != legacy_meta:
                        raise AssertionError(f"metadata drift: {label}/{case_id}")
                    observed_flags = tuple(
                        flag
                        for operation in plan.case(case_id).operations
                        if operation.op == "add_petsc_flags"
                        for flag in operation.argument_dict()["flags"]
                    )
                    if observed_flags != expected_flags[case_id]:
                        raise AssertionError(f"PETSc flag policy drift: {case_id}")
        except Exception as exc:
            failures.append(f"Issue62 equivalence: {exc}")
            print(f"ISSUE62_LEGACY_SPEC_EQUIVALENCE: FAIL ({exc})")
        else:
            print("ISSUE62_LEGACY_SPEC_EQUIVALENCE: PASS default+jacobian byte-identical")

        try:
            duplicate = base_inputs()["base"] + "[Debug]\n[]\n[Debug]\n[]\n"
            try:
                recipe.instrument_input(duplicate)
            except mb.MooseBlockError:
                pass
            else:
                raise AssertionError("legacy MooseBlockError contract was not preserved")
        except Exception as exc:
            failures.append(f"Issue62 error compatibility: {exc}")
            print(f"ISSUE62_ERROR_COMPATIBILITY: FAIL ({exc})")
        else:
            print("ISSUE62_ERROR_COMPATIBILITY: PASS")

        try:
            adapter_source = (ROOT / "recipes" / "issue43_coupling_diagnostic.py").read_text(
                encoding="utf-8"
            )
            forbidden_policy_literals = (*LEGACY_DIAGNOSTIC_FLAGS, *LEGACY_JACOBIAN_FLAGS)
            if any(token in adapter_source for token in forbidden_policy_literals):
                raise AssertionError("adapter duplicates PETSc policy literals")
            if "show_var_residual_norms = true" in adapter_source:
                raise AssertionError("adapter duplicates MOOSE Debug policy")
            required_delegation = ("load_json_file", "compile_spec", "apply_case_plan")
            if not all(token in adapter_source for token in required_delegation):
                raise AssertionError("adapter does not delegate through generic spec engine")
        except Exception as exc:
            failures.append(f"Issue62 JSON ownership: {exc}")
            print(f"ISSUE62_JSON_POLICY_OWNERSHIP: FAIL ({exc})")
        else:
            print("ISSUE62_JSON_POLICY_OWNERSHIP: PASS")

    # Preserve public compatibility/CLI owners byte-for-byte.
    try:
        for rel, expected_sha in COMPATIBILITY_BLOB_BASELINES.items():
            observed = git_blob_sha(ROOT / rel)
            if observed != expected_sha:
                raise AssertionError(f"compatibility owner drift: {rel} {observed}")
    except Exception as exc:
        failures.append(f"Issue62 compatibility surface: {exc}")
        print(f"ISSUE62_COMPATIBILITY_SURFACE: FAIL ({exc})")
    else:
        print("ISSUE62_COMPATIBILITY_SURFACE: PASS")

    # Issue63: machine-check remaining-recipe terminal classifications from Issue59 rules.
    try:
        readiness = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
        if readiness.get("schema_version") != 1:
            raise AssertionError("readiness schema_version must be 1")
        records = readiness.get("recipes")
        if not isinstance(records, dict) or set(records) != EXPECTED_REMAINING_RECIPES:
            raise AssertionError("remaining recipe set mismatch")
        if set(readiness.get("terminal_classifications", ())) != TERMINAL_CLASSES:
            raise AssertionError("terminal classification vocabulary mismatch")
        follow_up_groups = readiness.get("follow_up_groups")
        if not isinstance(follow_up_groups, dict) or set(follow_up_groups) != {
            "transform-vocabulary-v2-complex-construction",
            "hybrid-spec-plus-diagnostics-extraction",
            "spec-ready-recipe-migration",
        }:
            raise AssertionError("follow-up group set mismatch")

        census = load_module(CENSUS_MODULE_PATH, "issue59_inventory_for_issue63")
        for recipe_path, record in records.items():
            if not isinstance(record, dict):
                raise AssertionError(f"readiness record is not an object: {recipe_path}")
            missing = REQUIRED_READINESS_FIELDS - set(record)
            if missing:
                raise AssertionError(f"missing fields for {recipe_path}: {sorted(missing)}")
            if record["terminal_classification"] not in TERMINAL_CLASSES:
                raise AssertionError(f"invalid terminal class for {recipe_path}")
            expected, profile, transform_readiness = expected_recipe_class(census, recipe_path)
            if record["terminal_classification"] != expected:
                raise AssertionError(
                    f"classification mismatch for {recipe_path}: "
                    f"{record['terminal_classification']} != {expected}"
                )
            if record["follow_up_group"] not in follow_up_groups:
                raise AssertionError(f"unowned follow-up group for {recipe_path}")
            if not isinstance(record["follow_up_boundary"], str) or not record["follow_up_boundary"].strip():
                raise AssertionError(f"missing follow-up boundary for {recipe_path}")
            if not isinstance(record["compatibility_surface"], list) or not record["compatibility_surface"]:
                raise AssertionError(f"missing compatibility surface for {recipe_path}")
            if record["scientific_runtime_sensitivity"] not in {"LOW", "MEDIUM", "HIGH"}:
                raise AssertionError(f"invalid sensitivity for {recipe_path}")
            expected_v1_without_extension = not any(
                value in {"PARTIAL", "NO"} for value in transform_readiness
            )
            if bool(record["v1_without_extension"]) != expected_v1_without_extension:
                raise AssertionError(f"v1 extension flag mismatch for {recipe_path}")
            profile_text = ",".join(f"{key}={profile[key]}" for key in sorted(profile))
            readiness_text = ",".join(transform_readiness) if transform_readiness else "none"
            print(
                f"ISSUE63_RECIPE_CLASS: PASS {recipe_path} "
                f"class={expected} profile={profile_text} transforms={readiness_text}"
            )
    except Exception as exc:
        failures.append(f"Issue63 readiness classification: {exc}")
        print(f"ISSUE63_READINESS_CLASSIFICATION: FAIL ({exc})")
    else:
        print("ISSUE63_READINESS_CLASSIFICATION: PASS recipes=6")
        print("ISSUE63_FOLLOW_UP_PLAN: PASS groups=3")

    # Issue64: prove the capability statement without adding a case-specific Python recipe.
    try:
        generic_payload = {
            "schema_version": 1,
            "experiment_id": "new-bounded-experiment-without-python-recipe",
            "cases": [
                {
                    "case_id": "only",
                    "operations": [
                        {
                            "op": "set_parameter",
                            "path": "Executioner",
                            "name": "verbose",
                            "value": "true",
                        },
                        {
                            "op": "add_petsc_flags",
                            "flags": ["-ksp_converged_reason"],
                        },
                    ],
                }
            ],
        }
        generic_plan = compile_spec(load_payload(generic_payload))
        rendered = apply_case_plan(base_inputs()["base"], generic_plan.case("only"))
        if mp.get_parameter(rendered, "Executioner", "verbose") != "true":
            raise AssertionError("new experiment did not render through generic engine")
        if "-ksp_converged_reason" not in po.get_flags(rendered):
            raise AssertionError("new experiment PETSc policy was not applied")
    except Exception as exc:
        failures.append(f"Issue64 no-Python authoring capability: {exc}")
        print(f"ISSUE64_NO_PYTHON_AUTHORING_CAPABILITY: FAIL ({exc})")
    else:
        print("ISSUE64_NO_PYTHON_AUTHORING_CAPABILITY: PASS")

    try:
        if SUPPORTED_OPERATIONS != {
            "ensure_block",
            "set_parameter",
            "add_petsc_flags",
        }:
            raise AssertionError(f"unexpected v1 vocabulary: {sorted(SUPPORTED_OPERATIONS)}")
        generic_sources = []
        for directory in (ROOT / "qpx_harness" / "spec", ROOT / "qpx_harness" / "transforms"):
            generic_sources.extend(path for path in directory.glob("*.py") if path.is_file())
        combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in generic_sources)
        forbidden_issue_tokens = ("issue31", "issue43", "issue45", "issue46")
        if any(token in combined for token in forbidden_issue_tokens):
            raise AssertionError("issue-specific identity leaked into generic spec/transform owners")
        forbidden_dsl_tokens = ("embedded_python", "python_callback", "foreach", "eval(")
        if any(token in combined for token in forbidden_dsl_tokens):
            raise AssertionError("general-purpose programming semantics leaked into v1")
    except Exception as exc:
        failures.append(f"Issue64 architecture invariant: {exc}")
        print(f"ISSUE64_ARCHITECTURE_INVARIANTS: FAIL ({exc})")
    else:
        print("ISSUE64_ARCHITECTURE_INVARIANTS: PASS")

    # Reuse #60/#61 accepted static regression as part of the integration safety net.
    result_60_61 = run_subprocess([sys.executable, str(ISSUE60_61_GUARD)])
    if result_60_61.returncode != 0 or "ISSUE60_61_FINAL_GUARD: PASS" not in result_60_61.stdout:
        failures.append("Issue60/61 regression guard failed")
        print("ISSUE64_ISSUE60_61_REGRESSION: FAIL")
        print(result_60_61.stdout, end="")
        print(result_60_61.stderr, end="", file=sys.stderr)
    else:
        print("ISSUE64_ISSUE60_61_REGRESSION: PASS")

    # scripts/qpx.py self-test dispatches self_test() owners only; no scientific --run/P3 path.
    harness = run_subprocess([sys.executable, str(QPX_CLI), "self-test"])
    if harness.returncode != 0 or "QPX_HARNESS_SELFTEST: PASS" not in harness.stdout:
        failures.append("full QPX harness self-test failed")
        print("ISSUE64_QPX_HARNESS_SELFTEST: FAIL")
        print(harness.stdout, end="")
        print(harness.stderr, end="", file=sys.stderr)
    else:
        if "ISSUE43_COUPLING_DIAGNOSTIC_SELFTEST: PASS" not in harness.stdout:
            failures.append("Issue43 coupling self-test marker missing from full harness self-test")
            print("ISSUE62_EXISTING_SELFTEST_COMPATIBILITY: FAIL")
        else:
            print("ISSUE62_EXISTING_SELFTEST_COMPATIBILITY: PASS")
        print("ISSUE64_QPX_HARNESS_SELFTEST: PASS")

    print("ISSUE62_REFACTOR_EVRS: 0")
    print("ISSUE63_REFACTOR_EVRS: 0")
    print("ISSUE64_REFACTOR_EVRS: 0")
    print("ISSUE64_SCIENTIFIC_RUNTIME_P3_EVR: NOT_RUN")
    print("ISSUE64_FOLLOW_UP_TRANSFER: PENDING_ISSUE_ONLY_CLOSURE_PHASE groups=3")

    if failures:
        for failure in failures:
            print(f"ISSUE62_64_ERROR: {failure}")
        print("ISSUE62_64_FINAL_GUARD: FAIL")
        return 1

    print("ISSUE62_64_FINAL_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
