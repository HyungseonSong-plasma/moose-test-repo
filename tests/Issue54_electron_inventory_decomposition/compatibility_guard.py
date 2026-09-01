#!/usr/bin/env python3
"""Read-only M1 compatibility guard for Issue54.

The guard freezes the pre-refactor public/CLI/downstream surface and the
scientific constants that must not drift while electron_inventory_nullspace.py
is decomposed. It never invokes a QPX scientific runtime.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "qpx_harness" / "electron_inventory_nullspace.py"
FIRST_LINEAR = ROOT / "qpx_harness" / "issue45_first_linear.py"
QPX_CLI = ROOT / "scripts" / "qpx.py"

EXPECTED_FUNCTIONS = {
    "audit_closed_electron_structure",
    "audit_constrained_quasisteady_structure",
    "analyze_drift_schema_text",
    "analyze_constraint_schema_text",
    "_synthetic_constrained_input",
    "_build_constrained_quasisteady_input",
    "_base_case_context",
    "_evidence_root",
    "_stage_case",
    "run_preflight",
    "run_closure_preflight",
    "run_closure_runtime_preflight",
    "run_closure_runtime",
    "self_test",
    "main",
}
EXPECTED_FIRST_LINEAR_ATTRS = {
    "ElectronInventoryNullspaceError",
    "_base_case_context",
    "_build_constrained_quasisteady_input",
    "_evidence_root",
    "_stage_case",
    "_synthetic_constrained_input",
    "audit_constrained_quasisteady_structure",
}
EXPECTED_LITERALS = {
    "ISSUE": 45,
    "DT_REFERENCE": 1.0e-13,
    "STEPS": 1,
    "DRIFT_TYPE": "QPXFVElectrostaticDrift",
    "CONSTRAINT_TYPE": "FVIntegralValueConstraint",
    "LAMBDA_VARIABLE": "r45_inventory_lambda",
    "MACRO_AVG_POSTPROCESSOR": "r45_ne_macro_avg",
    "DEFAULT_MACRO_ELECTRON_AVG": 1.0e16,
    "C0_TARGET": 1.0e16,
    "C1_TARGET": 1.01e16,
    "CLOSURE_TARGET_REL_TOL": 1.0e-6,
    "CLOSURE_DELTA_REL_TOL": 5.0e-4,
    "INVENTORY_CONSISTENCY_REL_TOL": 1.0e-8,
}
EXPECTED_CLI_FLAGS = {
    "--self-test",
    "--preflight",
    "--closure-preflight",
    "--closure-runtime-preflight",
    "--closure-run",
}
EXPECTED_SELFTEST_MARKERS = {
    "ISSUE45_INVENTORY_NULLSPACE_SELFTEST: PASS",
    "ISSUE45_INVENTORY_CLOSURE_RUNTIME_SELFTEST: PASS",
}


def _literal_assignments(tree: ast.Module) -> dict[str, object]:
    result: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            try:
                result[target.id] = ast.literal_eval(value)
            except (ValueError, TypeError):
                pass
    return result


def _function_loc(tree: ast.Module, name: str) -> int:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return int(node.end_lineno or node.lineno) - node.lineno + 1
    return 0


def _first_linear_attrs() -> set[str]:
    tree = ast.parse(FIRST_LINEAR.read_text(), filename=str(FIRST_LINEAR))
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level > 0 and node.module is None:
            for alias in node.names:
                if alias.name == "electron_inventory_nullspace":
                    aliases.add(alias.asname or alias.name)
    attrs: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            attrs.add(node.attr)
    return attrs


def _qpx_cli_contract() -> tuple[set[str], bool]:
    source = QPX_CLI.read_text()
    tree = ast.parse(source, filename=str(QPX_CLI))
    symbols: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "qpx_harness.electron_inventory_nullspace"
        ):
            symbols.update(alias.name for alias in node.names)
    routed = (
        '"inventory-nullspace"' in source
        and "inventory_nullspace_main" in source
        and "inventory_nullspace_self_test" in source
    )
    return symbols, routed


def main() -> int:
    try:
        source = TARGET.read_text()
        tree = ast.parse(source, filename=str(TARGET))
        functions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        classes = {
            node.name for node in tree.body if isinstance(node, ast.ClassDef)
        }
        missing_functions = EXPECTED_FUNCTIONS - functions
        if missing_functions:
            raise AssertionError(f"missing canonical functions: {sorted(missing_functions)}")
        if "ElectronInventoryNullspaceError" not in classes:
            raise AssertionError("ElectronInventoryNullspaceError surface disappeared")

        literals = _literal_assignments(tree)
        drift = {
            name: {"expected": expected, "observed": literals.get(name)}
            for name, expected in EXPECTED_LITERALS.items()
            if literals.get(name) != expected
        }
        if drift:
            raise AssertionError(f"scientific constant drift: {drift}")

        missing_flags = EXPECTED_CLI_FLAGS - {
            flag for flag in EXPECTED_CLI_FLAGS if flag in source
        }
        if missing_flags:
            raise AssertionError(f"CLI flags disappeared: {sorted(missing_flags)}")
        missing_markers = EXPECTED_SELFTEST_MARKERS - {
            marker for marker in EXPECTED_SELFTEST_MARKERS if marker in source
        }
        if missing_markers:
            raise AssertionError(f"self-test markers disappeared: {sorted(missing_markers)}")

        first_linear_attrs = _first_linear_attrs()
        missing_downstream = EXPECTED_FIRST_LINEAR_ATTRS - first_linear_attrs
        if missing_downstream:
            raise AssertionError(
                f"Issue45 first-linear dependency surface drift: {sorted(missing_downstream)}"
            )

        cli_symbols, routed = _qpx_cli_contract()
        if not {"main", "self_test"}.issubset(cli_symbols) or not routed:
            raise AssertionError(
                f"scripts/qpx.py inventory-nullspace routing drift: symbols={sorted(cli_symbols)} routed={routed}"
            )

        print("ISSUE54_M1_TARGET_LOC:", len(source.splitlines()))
        print("ISSUE54_M1_SELFTEST_LOC:", _function_loc(tree, "self_test"))
        print(
            "ISSUE54_M1_FIRST_LINEAR_ATTRS:",
            ",".join(sorted(first_linear_attrs)),
        )
        print("ISSUE54_M1_SCIENTIFIC_CONSTANTS: PASS")
        print("ISSUE54_M1_CLI_SURFACE: PASS")
        print("ISSUE54_M1_FIRST_LINEAR_SURFACE: PASS")
        print("ISSUE54_M1_COMPATIBILITY_GUARD: PASS")
        return 0
    except Exception as exc:
        print(f"ISSUE54_M1_COMPATIBILITY_GUARD: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
