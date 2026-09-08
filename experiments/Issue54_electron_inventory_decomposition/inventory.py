#!/usr/bin/env python3
"""Read-only M0 decomposition inventory for Issue54.

This script accounts for every top-level symbol in
qpx_harness/electron_inventory_nullspace.py, records function LOC/calls,
classifies semantic ownership candidates, and discovers branch-local consumers.
It intentionally performs no repository or source mutation.
"""
from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "qpx_harness" / "electron_inventory_nullspace.py"
FIRST_LINEAR = ROOT / "qpx_harness" / "issue45_first_linear.py"
QPX_CLI = ROOT / "scripts" / "qpx.py"
SCAN_ROOTS = ("qpx_harness", "recipes", "scripts", "tests")

EXPECTED_FIRST_LINEAR_ATTRS = {
    "ElectronInventoryNullspaceError",
    "_base_case_context",
    "_build_constrained_quasisteady_input",
    "_evidence_root",
    "_stage_case",
    "_synthetic_constrained_input",
    "audit_constrained_quasisteady_structure",
}

STRUCTURE_NAMES = {
    "_unquote",
    "_words",
    "_parameter_value",
    "_parameter_count",
    "_set_or_insert_parameter",
    "_direct_children",
    "_truthy",
    "_remove_block",
    "_replace_block",
    "_ensure_debug_block",
    "_electron_kernel_records",
    "_electron_fvbcs",
    "_poisson_fvbcs",
    "_flux_boundary_audit",
    "_audit_poisson_grounding",
    "_float_parameter",
    "audit_closed_electron_structure",
    "audit_constrained_quasisteady_structure",
}
SCHEMA_NAMES = {
    "_extract_moose_json",
    "_schema_presence_analysis",
    "analyze_drift_schema_text",
    "analyze_constraint_schema_text",
}
CLOSURE_MODEL_NAMES = {
    "_synthetic_closed_input",
    "_synthetic_constrained_input",
    "_build_constrained_quasisteady_input",
    "_normalized_target_text",
    "_target_only_pair_audit",
}
RUNTIME_EVALUATION_NAMES = {
    "_synthetic_runtime_row",
    "_evaluate_runtime_case_data",
    "_evaluate_runtime_pair",
    "_find_runtime_csv",
    "_read_final_runtime_row",
}
ORCHESTRATION_NAMES = {
    "_write_json",
    "_stage_case",
    "_base_case_context",
    "_evidence_root",
    "_prepare_case",
    "_prepare_closure_case",
    "_prepare_closure_runtime_cases",
    "_run_p2_check_input",
    "_run_schema_query",
    "_closure_runtime_preflight_result",
    "_emit_closure_runtime_preflight_markers",
    "_runtime_case",
    "run_preflight",
    "run_closure_preflight",
    "run_closure_runtime_preflight",
    "run_closure_runtime",
}


def _read(path: Path) -> str:
    return path.read_text()


def _top_level(tree: ast.Module) -> list[ast.AST]:
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign))
    ]


def _node_end(node: ast.AST) -> int:
    return int(getattr(node, "end_lineno", getattr(node, "lineno", 0)))


def _assigned_names(node: ast.AST) -> list[str]:
    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets.extend(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets.append(node.target)
    names: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
    return names


def _category(name: str) -> str:
    if name == "self_test":
        return "characterization"
    if name == "main":
        return "facade/CLI"
    if name in STRUCTURE_NAMES:
        return "structure"
    if name in SCHEMA_NAMES or "schema" in name:
        return "schema"
    if name in CLOSURE_MODEL_NAMES:
        return "closure-model"
    if name in RUNTIME_EVALUATION_NAMES:
        return "runtime-evaluation"
    if name in ORCHESTRATION_NAMES:
        return "orchestration/evidence"
    if name.startswith("run_") or name.startswith("_prepare_") or name.startswith("_run_"):
        return "orchestration/evidence"
    if name.startswith("audit_"):
        return "structure"
    if "runtime" in name and ("evaluate" in name or "csv" in name or "row" in name):
        return "runtime-evaluation"
    if "target" in name or "constrained" in name:
        return "closure-model"
    return "shared-helper-candidate"


def _function_calls(node: ast.AST, top_functions: set[str]) -> list[str]:
    result: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            if child.func.id in top_functions:
                result.add(child.func.id)
    return sorted(result)


def _name_refs(node: ast.AST, constants: set[str]) -> list[str]:
    return sorted(
        {
            child.id
            for child in ast.walk(node)
            if isinstance(child, ast.Name) and child.id in constants
        }
    )


def _iter_python_files() -> Iterable[Path]:
    for rel in SCAN_ROOTS:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" not in path.parts and path != TARGET:
                yield path


def _module_aliases(tree: ast.Module, path: Path) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "qpx_harness.electron_inventory_nullspace":
                    aliases.add(alias.asname or alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module == "qpx_harness":
                for alias in node.names:
                    if alias.name == "electron_inventory_nullspace":
                        aliases.add(alias.asname or alias.name)
            if "qpx_harness" in path.parts and node.level > 0 and node.module is None:
                for alias in node.names:
                    if alias.name == "electron_inventory_nullspace":
                        aliases.add(alias.asname or alias.name)
    return aliases


def _direct_imported_symbols(tree: ast.Module) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 0 and node.module == "qpx_harness.electron_inventory_nullspace":
            result.update(alias.name for alias in node.names)
        elif node.level > 0 and node.module == "electron_inventory_nullspace":
            result.update(alias.name for alias in node.names)
    return result


def _consumer_inventory() -> dict[str, dict[str, object]]:
    consumers: dict[str, dict[str, object]] = {}
    for path in _iter_python_files():
        try:
            tree = ast.parse(_read(path), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        aliases = _module_aliases(tree, path)
        direct = _direct_imported_symbols(tree)
        attrs: set[str] = set()
        if aliases:
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id in aliases
                ):
                    attrs.add(node.attr)
        if aliases or direct:
            consumers[str(path.relative_to(ROOT))] = {
                "module_aliases": sorted(aliases),
                "direct_symbols": sorted(direct),
                "attribute_symbols": sorted(attrs),
            }
    return consumers


def _cli_contract(tree: ast.Module) -> dict[str, object]:
    direct = _direct_imported_symbols(tree)
    source = _read(QPX_CLI)
    return {
        "direct_symbols": sorted(direct),
        "has_inventory_nullspace_command": '"inventory-nullspace"' in source,
        "has_main_alias": "inventory_nullspace_main" in source,
        "has_self_test_alias": "inventory_nullspace_self_test" in source,
    }


def inventory() -> dict[str, object]:
    source = _read(TARGET)
    tree = ast.parse(source, filename=str(TARGET))
    lines = source.splitlines()

    function_nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    class_nodes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    top_functions = {node.name for node in function_nodes}

    constants: set[str] = set()
    assignments: dict[str, dict[str, object]] = {}
    for node in _top_level(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            for name in _assigned_names(node):
                assignments[name] = {
                    "line": int(getattr(node, "lineno", 0)),
                    "end_line": _node_end(node),
                    "constant": name.isupper(),
                }
                if name.isupper():
                    constants.add(name)

    functions: list[dict[str, object]] = []
    by_category: dict[str, list[str]] = defaultdict(list)
    category_constants: dict[str, set[str]] = defaultdict(set)
    for node in function_nodes:
        category = _category(node.name)
        by_category[category].append(node.name)
        refs = _name_refs(node, constants)
        category_constants[category].update(refs)
        functions.append(
            {
                "name": node.name,
                "line": node.lineno,
                "end_line": _node_end(node),
                "loc": _node_end(node) - node.lineno + 1,
                "category": category,
                "internal_calls": _function_calls(node, top_functions),
                "constants": refs,
            }
        )

    consumers = _consumer_inventory()
    first_linear = consumers.get("qpx_harness/issue45_first_linear.py", {})
    first_linear_attrs = set(first_linear.get("attribute_symbols", []))

    cli_tree = ast.parse(_read(QPX_CLI), filename=str(QPX_CLI))
    cli = _cli_contract(cli_tree)

    self_test = next((item for item in functions if item["name"] == "self_test"), None)
    public_functions = sorted(name for name in top_functions if not name.startswith("_"))
    public_classes = sorted(node.name for node in class_nodes if not node.name.startswith("_"))
    public_constants = sorted(name for name in constants if not name.startswith("_"))

    first_linear_ok = EXPECTED_FIRST_LINEAR_ATTRS.issubset(first_linear_attrs)
    cli_ok = (
        cli["has_inventory_nullspace_command"]
        and cli["has_main_alias"]
        and cli["has_self_test_alias"]
    )
    required_top = {
        "audit_closed_electron_structure",
        "audit_constrained_quasisteady_structure",
        "analyze_drift_schema_text",
        "analyze_constraint_schema_text",
        "run_preflight",
        "run_closure_preflight",
        "run_closure_runtime_preflight",
        "run_closure_runtime",
        "self_test",
        "main",
    }
    accounted = required_top.issubset(top_functions)

    return {
        "loc": len(lines),
        "sha_source_length": len(source.encode()),
        "functions": functions,
        "classes": [
            {
                "name": node.name,
                "line": node.lineno,
                "end_line": _node_end(node),
                "loc": _node_end(node) - node.lineno + 1,
            }
            for node in class_nodes
        ],
        "assignments": assignments,
        "public_surface": {
            "functions": public_functions,
            "classes": public_classes,
            "constants": public_constants,
        },
        "self_test_loc": self_test["loc"] if self_test else 0,
        "categories": {key: sorted(value) for key, value in sorted(by_category.items())},
        "category_constants": {
            key: sorted(value) for key, value in sorted(category_constants.items())
        },
        "consumers": consumers,
        "first_linear_expected_attrs": sorted(EXPECTED_FIRST_LINEAR_ATTRS),
        "first_linear_observed_attrs": sorted(first_linear_attrs),
        "first_linear_contract": "PASS" if first_linear_ok else "HOLD",
        "cli_contract": {**cli, "status": "PASS" if cli_ok else "HOLD"},
        "required_top_level_contract": "PASS" if accounted else "HOLD",
        "status": "PASS" if first_linear_ok and cli_ok and accounted else "HOLD",
    }


def _print_human(result: dict[str, object]) -> None:
    print("ISSUE54_M0_LOC:", result["loc"])
    print("ISSUE54_M0_SELFTEST_LOC:", result["self_test_loc"])
    print("ISSUE54_M0_FUNCTION_COUNT:", len(result["functions"]))
    print("ISSUE54_M0_CLASS_COUNT:", len(result["classes"]))
    print("ISSUE54_M0_FIRST_LINEAR_CONTRACT:", result["first_linear_contract"])
    print("ISSUE54_M0_CLI_CONTRACT:", result["cli_contract"]["status"])
    print("ISSUE54_M0_REQUIRED_TOP_LEVEL:", result["required_top_level_contract"])
    for category, names in result["categories"].items():
        print(f"ISSUE54_M0_CATEGORY: {category} count={len(names)} names={','.join(names)}")
    for item in result["functions"]:
        calls = ",".join(item["internal_calls"]) if item["internal_calls"] else "NONE"
        constants = ",".join(item["constants"]) if item["constants"] else "NONE"
        print(
            f"ISSUE54_M0_FUNCTION: {item['name']} "
            f"category={item['category']} line={item['line']} loc={item['loc']} "
            f"calls={calls} constants={constants}"
        )
    for path, consumer in sorted(result["consumers"].items()):
        attrs = ",".join(consumer["attribute_symbols"]) or "NONE"
        direct = ",".join(consumer["direct_symbols"]) or "NONE"
        print(f"ISSUE54_M0_CONSUMER: {path} attrs={attrs} direct={direct}")
    print("ISSUE54_M0_INVENTORY:", result["status"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = inventory()
    except Exception as exc:
        print(f"ISSUE54_M0_INVENTORY: FAIL ({exc})")
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        _print_human(result)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
