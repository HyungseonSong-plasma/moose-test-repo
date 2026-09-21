from __future__ import annotations

import ast
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose import petsc_options as po
from physics_harness.adapters.moose.mutation_spec import (
    MutationSpecError,
    compile_mutation_spec,
    load_mutation_payload,
)
from physics_harness.adapters.moose.mutation_spec.plan import OperationPlan
from physics_harness.adapters.moose.transforms import (
    SUPPORTED_OPERATIONS,
    TransformError,
    apply_case_plan,
    apply_operation,
)

EXPECTED_OPERATIONS = {
    "ensure_block", "set_parameter", "add_petsc_flags", "remove_block",
    "replace_block", "insert_child_block", "insert_top_level_before",
    "remove_paths", "remove_petsc_flags", "set_petsc_option",
    "remove_petsc_option",
}
HISTORICAL_COMMANDS = {
    "test", "test-all", "coupling-evr1", "coupling-evr2", "scale-audit",
    "fast-relaxation", "fast-coupling-diagnostic", "inventory-nullspace",
    "inventory-first-linear", "inventory-jacobian-localization",
    "inventory-fd-reference", "contract", "dmix-equivalence", "measure",
    "measure-smoke", "investigate", "transport-probe", "cache-audit",
    "profile", "analyze", "bundle", "inventory", "preflight",
    "temporal-csv", "self-test",
}
CURRENT_COMPAT_COMMANDS = {"test", "test-all", "contract", "measure", "analyze", "inventory"}
CURRENT_CANONICAL_COMMANDS = {"compile", "plan", "lower", "run", "preflight", "temporal-csv"}
HISTORICAL_OWNERSHIP_MODELS = {
    "SPEC_OWNED_COMPAT_ADAPTER",
    "HYBRID_SPEC_PLUS_PYTHON_POLICY",
    "PURE_PYTHON_SCIENTIFIC_POLICY",
    "RETIRED_AFTER_CONSUMER_PROOF",
}

CURRENT_OWNER_SYMBOLS = {
    "physics_harness/execution/runtime.py": {"resolve_executable", "run_physics"},
    "physics_harness/execution/cases.py": {"stage_case", "validate_case_references"},
    "physics_harness/execution/workspace.py": {"discover_manifests", "inventory_workspace"},
    "physics_harness/evidence/artifacts.py": {"write_json_bundle", "current_run_artifact"},
}
HISTORICAL_RECIPE_FILES = (
    "experiments/historical_recipe_support/issue43_coupling_diagnostic.py",
    "experiments/historical_recipe_support/issue45_first_linear.py",
    "experiments/historical_recipe_support/issue46_jacobian_localization.py",
)
RETIRED_CAMPAIGN_PATHS = (
    "physics_harness/issue43_coupling_diagnostic.py",
    "physics_harness/issue45_first_linear.py",
    "physics_harness/issue46_jacobian_localization.py",
    "physics_harness/coupling_evr1_runtime.py",
    "physics_harness/coupling_evr2_runtime.py",
    "physics_harness/dmix_equivalence.py",
)

SYNTHETIC = """[Variables]\n  [u]\n    type = MooseVariableFVReal\n  []\n  [drop]\n    type = MooseVariableFVReal\n  []\n[]\n[FVKernels]\n  [keep]\n    type = FVDiffusion\n    variable = u\n  []\n  [drop_kernel]\n    type = FVDiffusion\n    variable = drop\n  []\n[]\n[Executioner]\n  type = Transient\n  petsc_options = '-keep -remove'\n  petsc_options_iname = '-pc_type -mat_fd_type'\n  petsc_options_value = 'lu wp'\n[]\n[Outputs]\n  [console]\n    type = Console\n  []\n[]\n"""
COUPLING_BASE = """[Executioner]\n  type = Transient\n  petsc_options = '-existing'\n[]\n[Outputs]\n  [console]\n    type = Console\n  []\n[]\n"""
FIRST_LINEAR_BASE = """[Executioner]\n  type = Steady\n  petsc_options = '-existing'\n[]\n[Outputs]\n  [console]\n    type = Console\n  []\n[]\n"""
LOCALIZATION_BASE = """[Executioner]\n  type = Steady\n  nl_max_its = 1\n  petsc_options = '-snes_converged_reason -snes_test_jacobian -ksp_view'\n  petsc_options_iname = '-pc_type'\n  petsc_options_value = 'lu'\n[]\n[Outputs]\n  [console]\n    type = Console\n  []\n[]\n"""

ISSUE43_PAYLOAD = {
    "schema_version": 1, "experiment_id": "issue43-coupling-diagnostic",
    "cases": [{"case_id": "default", "operations": [
        {"op": "ensure_block", "path": "Debug", "block": "[Debug]\n  show_var_residual_norms = true\n[]"},
        {"op": "set_parameter", "path": "Debug", "name": "show_var_residual_norms", "value": "true"},
        {"op": "set_parameter", "path": "Executioner", "name": "verbose", "value": "true"},
        {"op": "add_petsc_flags", "flags": ["-snes_converged_reason", "-ksp_converged_reason", "-snes_monitor", "-ksp_monitor"]},
        {"op": "set_parameter", "path": "Outputs/console", "name": "all_variable_norms", "value": "true"},
    ]}, {"case_id": "jacobian", "operations": [
        {"op": "ensure_block", "path": "Debug", "block": "[Debug]\n  show_var_residual_norms = true\n[]"},
        {"op": "set_parameter", "path": "Debug", "name": "show_var_residual_norms", "value": "true"},
        {"op": "set_parameter", "path": "Executioner", "name": "verbose", "value": "true"},
        {"op": "add_petsc_flags", "flags": ["-snes_converged_reason", "-ksp_converged_reason", "-snes_monitor", "-ksp_monitor", "-snes_test_jacobian"]},
        {"op": "set_parameter", "path": "Outputs/console", "name": "all_variable_norms", "value": "true"},
    ]}],
}
ISSUE45_PAYLOAD = {
    "schema_version": 1, "experiment_id": "issue45_first_linear",
    "cases": [{"case_id": "first_linear", "operations": [
        {"op": "set_parameter", "path": "Executioner", "name": "nl_max_its", "value": "1"},
        {"op": "add_petsc_flags", "flags": ["-snes_converged_reason", "-ksp_converged_reason"]},
        {"op": "add_petsc_flags", "flags": ["-snes_test_jacobian", "-ksp_view", "-ksp_monitor_true_residual"]},
    ]}],
}
ISSUE46_PAYLOAD = {
    "schema_version": 1, "experiment_id": "issue46_jacobian_localization",
    "cases": [{"case_id": "localization", "operations": [
        {"op": "remove_petsc_flags", "flags": ["-snes_test_jacobian"]},
        {"op": "add_petsc_flags", "flags": ["-snes_test_jacobian_view"]},
        {"op": "set_petsc_option", "name": "-snes_test_jacobian", "value": "1e-07"},
        {"op": "insert_child_block", "parent": "Outputs", "path": "Outputs/r46_dofmap", "block": "  [r46_dofmap]\n    type = DOFMap\n    execute_on = INITIAL\n    file_base = r46_dofmap\n  []"},
    ]}],
}


def _functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _literal_dict_keys(path: Path, name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            value = ast.literal_eval(node.value)
            if not isinstance(value, dict):
                raise AssertionError(f"{name} is not a literal dict")
            return set(value)
    raise AssertionError(f"missing {name}")


def _legacy_issue43(text: str, *, jacobian_test: bool) -> str:
    out = mb.append_top_level_block(text, "[Debug]\n  show_var_residual_norms = true\n[]")
    out = mp.upsert_parameter(out, "Executioner", "verbose", "true")
    flags = ["-snes_converged_reason", "-ksp_converged_reason", "-snes_monitor", "-ksp_monitor"]
    if jacobian_test:
        flags.append("-snes_test_jacobian")
    out = po.add_flags(out, flags)
    return mp.upsert_parameter(out, "Outputs/console", "all_variable_norms", "true")


def _legacy_issue45(text: str) -> str:
    out = mp.upsert_parameter(text, "Executioner", "nl_max_its", "1")
    return po.add_flags(out, ("-snes_converged_reason", "-ksp_converged_reason", "-snes_test_jacobian", "-ksp_view", "-ksp_monitor_true_residual"))


def _legacy_issue46(text: str) -> str:
    out = po.remove_flags(text, ["-snes_test_jacobian"])
    out = po.add_flags(out, ["-snes_test_jacobian_view"])
    out = po.upsert_name_value(out, "-snes_test_jacobian", "1e-07")
    return mb.insert_child_block(out, "Outputs", "  [r46_dofmap]\n    type = DOFMap\n    execute_on = INITIAL\n    file_base = r46_dofmap\n  []")


def _check_bounded_transforms() -> None:
    assert set(SUPPORTED_OPERATIONS) == EXPECTED_OPERATIONS
    invalid = {"schema_version": 1, "experiment_id": "bad", "cases": [{"case_id": "bad", "operations": [{"op": "arbitrary_python"}]}]}
    try:
        load_mutation_payload(invalid)
    except MutationSpecError:
        pass
    else:
        raise AssertionError("unknown operation accepted")

    text = SYNTHETIC
    text = apply_operation(text, OperationPlan("ensure_block", (("path", "Debug"), ("block", "[Debug]\n[]"))))
    text = apply_operation(text, OperationPlan("set_parameter", (("path", "Debug"), ("name", "show_var_residual_norms"), ("value", "true"))))
    text = apply_operation(text, OperationPlan("add_petsc_flags", (("flags", ("-new",)), ("path", "Executioner"), ("parameter", "petsc_options"))))
    text = apply_operation(text, OperationPlan("remove_block", (("path", "FVKernels/drop_kernel"),)))
    text = apply_operation(text, OperationPlan("replace_block", (("path", "FVKernels/keep"), ("block", "  [keep]\n    type = FVDiffusion\n    variable = u\n    coeff = 2\n  []"))))
    text = apply_operation(text, OperationPlan("insert_child_block", (("parent", "Outputs"), ("path", "Outputs/new_console"), ("block", "  [new_console]\n    type = Console\n  []"))))
    text = apply_operation(text, OperationPlan("insert_top_level_before", (("marker", "Outputs"), ("block", "[Extra]\n[]"))))
    text = apply_operation(text, OperationPlan("remove_paths", (("paths", ("Variables/drop",)),)))
    text = apply_operation(text, OperationPlan("remove_petsc_flags", (("flags", ("-remove",)), ("path", "Executioner"), ("parameter", "petsc_options"))))
    text = apply_operation(text, OperationPlan("set_petsc_option", (("name", "-mat_fd_type"), ("value", "ds"), ("path", "Executioner"), ("names_parameter", "petsc_options_iname"), ("values_parameter", "petsc_options_value"))))
    text = apply_operation(text, OperationPlan("remove_petsc_option", (("name", "-mat_fd_type"), ("path", "Executioner"), ("names_parameter", "petsc_options_iname"), ("values_parameter", "petsc_options_value"))))
    assert mb.has_block(text, "Debug") and mb.has_block(text, "Outputs/new_console")
    assert not mb.has_block(text, "FVKernels/drop_kernel") and not mb.has_block(text, "Variables/drop")
    assert mp.get_parameter(text, "FVKernels/keep", "coeff") == "2"
    assert "-new" in po.get_flags(text) and "-remove" not in po.get_flags(text)
    assert all(name != "-mat_fd_type" for name, _ in po.get_name_value_pairs(text))
    try:
        apply_operation(text, OperationPlan("arbitrary_python"))
    except TransformError:
        pass
    else:
        raise AssertionError("transform registry accepted arbitrary operation")


def _check_spec_equivalence() -> None:
    p43 = compile_mutation_spec(load_mutation_payload(ISSUE43_PAYLOAD))
    for jac, case in ((False, "default"), (True, "jacobian")):
        assert apply_case_plan(COUPLING_BASE, p43.case(case)) == _legacy_issue43(COUPLING_BASE, jacobian_test=jac)
    p45 = compile_mutation_spec(load_mutation_payload(ISSUE45_PAYLOAD))
    assert apply_case_plan(FIRST_LINEAR_BASE, p45.case("first_linear")) == _legacy_issue45(FIRST_LINEAR_BASE)
    p46 = compile_mutation_spec(load_mutation_payload(ISSUE46_PAYLOAD))
    assert apply_case_plan(LOCALIZATION_BASE, p46.case("localization")) == _legacy_issue46(LOCALIZATION_BASE)

    for rel in HISTORICAL_RECIPE_FILES:
        source = (ROOT / rel).read_text(encoding="utf-8")
        assert "qpx_harness" not in source, rel
        assert "physics_harness" in source, rel
        assert "compile_mutation_spec" in source and "apply_case_plan" in source, rel


def _check_current_ownership() -> None:
    assert HISTORICAL_OWNERSHIP_MODELS == {
        "SPEC_OWNED_COMPAT_ADAPTER", "HYBRID_SPEC_PLUS_PYTHON_POLICY",
        "PURE_PYTHON_SCIENTIFIC_POLICY", "RETIRED_AFTER_CONSUMER_PROOF",
    }
    for rel, required in CURRENT_OWNER_SYMBOLS.items():
        path = ROOT / rel
        assert path.is_file(), rel
        missing = required - _functions(path)
        assert not missing, (rel, missing)
        assert "qpx_harness" not in path.read_text(encoding="utf-8"), rel
    assert not (ROOT / "qpx_harness").exists()
    resurrected = [rel for rel in RETIRED_CAMPAIGN_PATHS if (ROOT / rel).exists()]
    assert not resurrected, resurrected


def _check_cli_retirement() -> None:
    assert len(HISTORICAL_COMMANDS) == 25
    path = ROOT / "physics_harness/cli/app.py"
    assert _literal_dict_keys(path, "COMMANDS") == CURRENT_COMPAT_COMMANDS
    assert _literal_dict_keys(path, "CANONICAL_COMMANDS") == CURRENT_CANONICAL_COMMANDS
    retired = HISTORICAL_COMMANDS - CURRENT_COMPAT_COMMANDS - CURRENT_CANONICAL_COMMANDS
    source = path.read_text(encoding="utf-8")
    for command in retired:
        if command in {"preflight", "temporal-csv"}:
            continue
        assert f'"{command}"' not in source, command
    assert "qpx_harness" not in source
    assert not (ROOT / "scripts").exists()


def main() -> int:
    failures: list[str] = []
    for label, func in (
        ("ISSUE66_BOUNDED_TRANSFORMS", _check_bounded_transforms),
        ("ISSUE67_68_SPEC_DIAGNOSTICS", _check_spec_equivalence),
        ("ISSUE70_72_73_OWNERSHIP", _check_current_ownership),
        ("ISSUE74_75_CLI_RETIREMENT", _check_cli_retirement),
    ):
        try:
            func()
        except Exception as exc:
            failures.append(f"{label}: {exc}")
            print(f"{label}: FAIL ({exc})")
        else:
            suffix = " operations=11" if label == "ISSUE66_BOUNDED_TRANSFORMS" else ""
            print(f"{label}: PASS{suffix}")

    integration_ok = not failures
    print(f"ISSUE76_INTEGRATION: {'PASS' if integration_ok else 'FAIL'}")
    print("ISSUE66_76_SCIENTIFIC_RUNTIME_P3_EVR: NOT_RUN")
    print("ISSUE66_76_EXTERNAL_VALIDATION_ROUND: 1")
    if failures:
        for failure in failures:
            print(f"ISSUE66_76_ERROR: {failure}")
        print("ISSUE66_76_FINAL_GUARD: FAIL")
        return 1
    print("ISSUE66_76_FINAL_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
