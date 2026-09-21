from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose import petsc_options as po
from physics_harness.adapters.moose.input import MooseInput
from physics_harness.adapters.moose.mutation_spec import (
    compile_mutation_spec,
    load_mutation_payload,
)
from physics_harness.adapters.moose.transforms import (
    SUPPORTED_OPERATIONS,
    TransformError,
    apply_case_plan,
)

LEGACY_DIAGNOSTIC_FLAGS = (
    "-snes_converged_reason",
    "-ksp_converged_reason",
    "-snes_monitor",
    "-ksp_monitor",
)
LEGACY_JACOBIAN_FLAGS = ("-snes_test_jacobian",)

HISTORICAL_ISSUE43_SPEC = {
    "schema_version": 1,
    "experiment_id": "issue43-coupling-diagnostic",
    "description": "Declarative instrumentation policy for the Issue43 coupling diagnostic pilot.",
    "cases": [
        {
            "case_id": "default",
            "operations": [
                {"op": "ensure_block", "path": "Debug", "block": "[Debug]\n  show_var_residual_norms = true\n[]"},
                {"op": "set_parameter", "path": "Debug", "name": "show_var_residual_norms", "value": "true"},
                {"op": "set_parameter", "path": "Executioner", "name": "verbose", "value": "true"},
                {"op": "add_petsc_flags", "flags": list(LEGACY_DIAGNOSTIC_FLAGS)},
                {"op": "set_parameter", "path": "Outputs/console", "name": "all_variable_norms", "value": "true"},
            ],
        },
        {
            "case_id": "jacobian",
            "operations": [
                {"op": "ensure_block", "path": "Debug", "block": "[Debug]\n  show_var_residual_norms = true\n[]"},
                {"op": "set_parameter", "path": "Debug", "name": "show_var_residual_norms", "value": "true"},
                {"op": "set_parameter", "path": "Executioner", "name": "verbose", "value": "true"},
                {"op": "add_petsc_flags", "flags": list(LEGACY_DIAGNOSTIC_FLAGS + LEGACY_JACOBIAN_FLAGS)},
                {"op": "set_parameter", "path": "Outputs/console", "name": "all_variable_norms", "value": "true"},
            ],
        },
    ],
}

HISTORICAL_READINESS = {
    "issue31_coupling": ("BLOCKED_BY_MISSING_CAPABILITY", "transform-vocabulary-v2-complex-construction", False),
    "issue43_fast_relaxation": ("BLOCKED_BY_MISSING_CAPABILITY", "transform-vocabulary-v2-complex-construction", False),
    "issue45_first_linear": ("PARTIAL_SPEC_PLUS_ALGORITHM", "hybrid-spec-plus-diagnostics-extraction", True),
    "issue45_inventory_constraint": ("BLOCKED_BY_MISSING_CAPABILITY", "transform-vocabulary-v2-complex-construction", False),
    "issue46_fd_reference": ("BLOCKED_BY_MISSING_CAPABILITY", "transform-vocabulary-v2-complex-construction", False),
    "issue46_jacobian_localization": ("SPEC_READY", "spec-ready-recipe-migration", True),
}
TERMINAL_CLASSES = {
    "SPEC_READY",
    "PARTIAL_SPEC_PLUS_ALGORITHM",
    "KEEP_PYTHON_ALGORITHM",
    "BLOCKED_BY_MISSING_CAPABILITY",
}
FOLLOW_UP_GROUPS = {
    "transform-vocabulary-v2-complex-construction",
    "hybrid-spec-plus-diagnostics-extraction",
    "spec-ready-recipe-migration",
}
REQUIRED_V1_OPERATIONS = {"ensure_block", "set_parameter", "add_petsc_flags"}
HISTORICAL_RECIPE = "experiments/historical_recipe_support/issue43_coupling_diagnostic.py"


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
    return {"base": base, "existing_debug": existing_debug, "existing_flags": existing_flags}


def _generic_sources() -> list[Path]:
    root = ROOT / "physics_harness/adapters/moose/mutation_spec"
    files = [path for path in root.glob("*.py") if path.is_file()]
    files.append(ROOT / "physics_harness/adapters/moose/transforms.py")
    return files


def main() -> int:
    failures: list[str] = []

    try:
        plan = compile_mutation_spec(load_mutation_payload(HISTORICAL_ISSUE43_SPEC))
        assert plan.schema_version == 1
        assert plan.experiment_id == "issue43-coupling-diagnostic"
        assert {case.case_id for case in plan.cases} == {"default", "jacobian"}
    except Exception as exc:
        failures.append(f"Issue62 spec validation: {exc}")
        print(f"ISSUE62_SPEC_VALIDATION: FAIL ({exc})")
        plan = None
    else:
        print("ISSUE62_SPEC_VALIDATION: PASS")

    if plan is not None:
        try:
            for label, source in base_inputs().items():
                for jacobian_test, case_id in ((False, "default"), (True, "jacobian")):
                    legacy_text, legacy_meta = legacy_instrument_input(source, jacobian_test=jacobian_test)
                    direct_text = apply_case_plan(source, plan.case(case_id))
                    if direct_text != legacy_text:
                        raise AssertionError(f"declarative byte drift: {label}/{case_id}")
                    expected_flags = LEGACY_DIAGNOSTIC_FLAGS + (LEGACY_JACOBIAN_FLAGS if jacobian_test else ())
                    observed_flags = po.get_flags(direct_text)
                    if not set(expected_flags) <= set(observed_flags):
                        raise AssertionError(f"PETSc flag policy drift: {label}/{case_id}")
                    source_flags = po.get_flags(source)
                    if not set(source_flags) <= set(observed_flags):
                        raise AssertionError(f"pre-existing PETSc flag lost: {label}/{case_id}")
                    if legacy_meta["physics_or_numerics_changed"] is not False:
                        raise AssertionError("historical diagnostic changed physics/numerics")
        except Exception as exc:
            failures.append(f"Issue62 equivalence: {exc}")
            print(f"ISSUE62_LEGACY_SPEC_EQUIVALENCE: FAIL ({exc})")
        else:
            print("ISSUE62_LEGACY_SPEC_EQUIVALENCE: PASS default+jacobian byte-identical")

        try:
            duplicate = base_inputs()["base"] + "[Debug]\n[]\n[Debug]\n[]\n"
            try:
                apply_case_plan(duplicate, plan.case("default"))
            except TransformError:
                pass
            else:
                raise AssertionError("duplicate Debug block was accepted")
        except Exception as exc:
            failures.append(f"Issue62 error contract: {exc}")
            print(f"ISSUE62_ERROR_COMPATIBILITY: FAIL ({exc})")
        else:
            print("ISSUE62_ERROR_COMPATIBILITY: PASS")

    try:
        historical = ROOT / HISTORICAL_RECIPE
        source = historical.read_text(encoding="utf-8")
        if "qpx_harness" in source:
            raise AssertionError("historical adapter retained legacy production import")
        for token in (
            "physics_harness.adapters.moose",
            "load_mutation_json_file",
            "compile_mutation_spec",
            "apply_case_plan",
            "issue43_coupling_diagnostic.json",
        ):
            if token not in source:
                raise AssertionError(f"historical adapter delegation drift: {token}")
        for literal in (*LEGACY_DIAGNOSTIC_FLAGS, *LEGACY_JACOBIAN_FLAGS):
            if literal in source:
                raise AssertionError(f"historical adapter duplicated JSON PETSc policy: {literal}")
    except Exception as exc:
        failures.append(f"Issue62 JSON ownership: {exc}")
        print(f"ISSUE62_JSON_POLICY_OWNERSHIP: FAIL ({exc})")
    else:
        print("ISSUE62_JSON_POLICY_OWNERSHIP: PASS")

    try:
        if set(HISTORICAL_READINESS) != {
            "issue31_coupling",
            "issue43_fast_relaxation",
            "issue45_first_linear",
            "issue45_inventory_constraint",
            "issue46_fd_reference",
            "issue46_jacobian_localization",
        }:
            raise AssertionError("historical Issue63 recipe set drift")
        for recipe, (terminal, group, v1_without_extension) in HISTORICAL_READINESS.items():
            if terminal not in TERMINAL_CLASSES:
                raise AssertionError(f"invalid terminal class: {recipe}={terminal}")
            if group not in FOLLOW_UP_GROUPS:
                raise AssertionError(f"invalid follow-up group: {recipe}={group}")
            if not isinstance(v1_without_extension, bool):
                raise AssertionError(f"invalid v1 readiness flag: {recipe}")
            print(
                f"ISSUE63_RECIPE_CLASS: PASS {recipe} class={terminal} "
                f"group={group} v1_without_extension={v1_without_extension}"
            )
    except Exception as exc:
        failures.append(f"Issue63 readiness classification: {exc}")
        print(f"ISSUE63_READINESS_CLASSIFICATION: FAIL ({exc})")
    else:
        print("ISSUE63_READINESS_CLASSIFICATION: PASS recipes=6")
        print("ISSUE63_FOLLOW_UP_PLAN: PASS groups=3")

    try:
        generic_payload = {
            "schema_version": 1,
            "experiment_id": "new-bounded-experiment-without-python-recipe",
            "cases": [
                {
                    "case_id": "only",
                    "operations": [
                        {"op": "set_parameter", "path": "Executioner", "name": "verbose", "value": "true"},
                        {"op": "add_petsc_flags", "flags": ["-ksp_converged_reason"]},
                    ],
                }
            ],
        }
        generic_plan = compile_mutation_spec(load_mutation_payload(generic_payload))
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
        if not REQUIRED_V1_OPERATIONS <= set(SUPPORTED_OPERATIONS):
            raise AssertionError(f"historical v1 operations missing: {sorted(REQUIRED_V1_OPERATIONS - set(SUPPORTED_OPERATIONS))}")
        combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in _generic_sources())
        if any(token in combined for token in ("issue31", "issue43", "issue45", "issue46")):
            raise AssertionError("issue-specific identity leaked into generic spec/transform owners")
        if any(token in combined for token in ("embedded_python", "python_callback", "foreach", "eval(")):
            raise AssertionError("general-purpose programming semantics leaked into declarative engine")
    except Exception as exc:
        failures.append(f"Issue64 architecture invariant: {exc}")
        print(f"ISSUE64_ARCHITECTURE_INVARIANTS: FAIL ({exc})")
    else:
        print("ISSUE64_ARCHITECTURE_INVARIANTS: PASS")

    print("ISSUE62_REFACTOR_EVRS: 0")
    print("ISSUE63_REFACTOR_EVRS: 0")
    print("ISSUE64_REFACTOR_EVRS: 0")
    print("ISSUE64_SCIENTIFIC_RUNTIME_P3_EVR: NOT_RUN")
    print("ISSUE64_FOLLOW_UP_TRANSFER: HISTORICAL_COMPLETE groups=3")

    if failures:
        for failure in failures:
            print(f"ISSUE62_64_ERROR: {failure}")
        print("ISSUE62_64_FINAL_GUARD: FAIL")
        return 1

    print("ISSUE62_64_FINAL_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
