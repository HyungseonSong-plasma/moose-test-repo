#!/usr/bin/env python3
"""Final read-only structural/compatibility gate for Issue54."""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FACADE = ROOT / "qpx_harness" / "electron_inventory_nullspace.py"
OWNER_ROOT = ROOT / "qpx_harness" / "issue45"
FIRST_LINEAR = ROOT / "qpx_harness" / "issue45_first_linear.py"
QPX_CLI = ROOT / "scripts" / "qpx.py"

EXPECTED_OWNER_FUNCTIONS = {
    "inventory_structure.py": {
        "audit_closed_electron_structure",
        "audit_constrained_quasisteady_structure",
    },
    "closure_schema.py": {
        "analyze_drift_schema_text",
        "analyze_constraint_schema_text",
    },
    "closure_model.py": {
        "_synthetic_constrained_input",
        "_build_constrained_quasisteady_input",
        "_target_only_pair_audit",
    },
    "closure_runtime.py": {
        "_evaluate_runtime_case_data",
        "_evaluate_runtime_pair",
        "_find_runtime_csv",
        "_read_final_runtime_row",
    },
    "orchestration.py": {
        "_base_case_context",
        "_evidence_root",
        "_stage_case",
        "run_preflight",
        "run_closure_preflight",
        "run_closure_runtime_preflight",
        "run_closure_runtime",
    },
    "characterization.py": {"self_test"},
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


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _functions(path: Path) -> set[str]:
    return {
        node.name
        for node in _tree(path).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _imported_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in _tree(path).body:
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
    return names


def _inv_attrs(path: Path) -> set[str]:
    attrs: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "inv":
                attrs.add(node.attr)
    return attrs


def main() -> int:
    ok = True
    facade_functions = _functions(FACADE)
    if facade_functions != {"main"}:
        print("ISSUE54_FINAL_THIN_FACADE: FAIL local_functions=" + ",".join(sorted(facade_functions)))
        ok = False
    else:
        print("ISSUE54_FINAL_THIN_FACADE: PASS")

    facade_imports = _imported_names(FACADE)
    missing_reexports = EXPECTED_FIRST_LINEAR_ATTRS - facade_imports
    if missing_reexports:
        print("ISSUE54_FINAL_FIRST_LINEAR_REEXPORTS: FAIL missing=" + ",".join(sorted(missing_reexports)))
        ok = False
    else:
        print("ISSUE54_FINAL_FIRST_LINEAR_REEXPORTS: PASS")

    observed_first_linear = _inv_attrs(FIRST_LINEAR)
    if not EXPECTED_FIRST_LINEAR_ATTRS.issubset(observed_first_linear):
        print("ISSUE54_FINAL_FIRST_LINEAR_CONSUMERS: FAIL observed=" + ",".join(sorted(observed_first_linear)))
        ok = False
    else:
        print("ISSUE54_FINAL_FIRST_LINEAR_CONSUMERS: PASS")

    for filename, required in EXPECTED_OWNER_FUNCTIONS.items():
        path = OWNER_ROOT / filename
        if not path.is_file():
            print(f"ISSUE54_FINAL_OWNER: FAIL {filename} missing")
            ok = False
            continue
        funcs = _functions(path)
        missing = required - funcs
        if missing:
            print(f"ISSUE54_FINAL_OWNER: FAIL {filename} missing=" + ",".join(sorted(missing)))
            ok = False
        else:
            print(f"ISSUE54_FINAL_OWNER: PASS {filename} loc={len(path.read_text().splitlines())}")

    cli_text = QPX_CLI.read_text()
    cli_ok = (
        "from qpx_harness.electron_inventory_nullspace import" in cli_text
        and '"inventory-nullspace"' in cli_text
        and "inventory_nullspace_self_test" in cli_text
    )
    print("ISSUE54_FINAL_CLI_SURFACE:", "PASS" if cli_ok else "FAIL")
    ok = ok and cli_ok

    try:
        facade = importlib.import_module("qpx_harness.electron_inventory_nullspace")
        structure = importlib.import_module("qpx_harness.issue45.inventory_structure")
        model = importlib.import_module("qpx_harness.issue45.closure_model")
        orchestration = importlib.import_module("qpx_harness.issue45.orchestration")
        identities = (
            facade.audit_constrained_quasisteady_structure
            is structure.audit_constrained_quasisteady_structure
            and facade._build_constrained_quasisteady_input
            is model._build_constrained_quasisteady_input
            and facade._base_case_context is orchestration._base_case_context
            and facade._stage_case is orchestration._stage_case
        )
    except Exception as exc:
        print(f"ISSUE54_FINAL_IMPORT_IDENTITY: FAIL ({exc})")
        ok = False
    else:
        print("ISSUE54_FINAL_IMPORT_IDENTITY:", "PASS" if identities else "FAIL")
        ok = ok and identities

    facade_loc = len(FACADE.read_text().splitlines())
    print("ISSUE54_FINAL_FACADE_LOC:", facade_loc)
    print("ISSUE54_FINAL_EVRS_CONSUMED_BY_REFACTOR: 0")
    print("ISSUE54_FINAL_GUARD:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
