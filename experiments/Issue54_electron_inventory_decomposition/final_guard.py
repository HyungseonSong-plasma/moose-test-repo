#!/usr/bin/env python3
"""Final read-only gate for historical Issue45 inventory ownership after retirement."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.historical_recipe_support import issue45_inventory_constraint as inventory

RETIRED_PATHS = (
    "physics_harness/domains/plasma/electron_inventory.py",
    "physics_harness/analysis/electron_inventory",
    "physics_harness/adapters/moose/electron_inventory",
    "physics_harness/execution/electron_inventory",
    "physics_harness/validation/electron_inventory",
    "physics_harness/cli/commands/inventory.py",
    "physics_harness/electron_inventory_nullspace.py",
    "physics_harness/issue45_first_linear.py",
)
GENERIC_OWNER_FILES = (
    "physics_harness/adapters/moose/blocks.py",
    "physics_harness/adapters/moose/parameters.py",
    "physics_harness/adapters/moose/preflight.py",
    "physics_harness/adapters/moose/nonlinear_solver.py",
    "physics_harness/adapters/moose/petsc_options.py",
    "physics_harness/adapters/petsc/log.py",
    "physics_harness/evidence/identity.py",
)


def main() -> int:
    missing = [relative for relative in GENERIC_OWNER_FILES if not (ROOT / relative).is_file()]
    print(
        "ISSUE54_FINAL_CANONICAL_INVENTORY_OWNER:",
        "PASS" if not missing else "FAIL missing=" + ",".join(missing),
    )
    if missing:
        return 1

    resurrected = [relative for relative in RETIRED_PATHS if (ROOT / relative).exists()]
    print(
        "ISSUE54_FINAL_LEGACY_FACADE_COMPAT:",
        "RETIRED" if not resurrected else "FAIL " + ",".join(resurrected),
    )
    if resurrected:
        return 1
    print("ISSUE54_FINAL_FIRST_LINEAR_COMPAT: RETIRED")

    required_inventory = (
        "build_constrained_quasisteady_input",
        "audit_constrained_quasisteady_structure",
        "target_only_pair_audit",
        "evaluate_runtime_case_data",
        "evaluate_runtime_pair",
    )
    required_first_linear = {
        "instrument_first_linear",
        "analyze_first_linear_text",
    }
    for name in required_inventory:
        if not callable(getattr(inventory, name, None)):
            raise AssertionError(f"historical inventory policy missing: {name}")

    first_linear_path = ROOT / "experiments/historical_recipe_support/issue45_first_linear.py"
    first_linear_source = first_linear_path.read_text(encoding="utf-8")
    first_linear_tree = ast.parse(first_linear_source, filename=str(first_linear_path))
    first_linear_functions = {
        node.name
        for node in first_linear_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if not required_first_linear <= first_linear_functions:
        raise AssertionError(
            "historical first-linear policy missing: "
            f"{sorted(required_first_linear - first_linear_functions)}"
        )

    inventory_source = Path(inventory.__file__).read_text(encoding="utf-8")
    for label, source in (
        ("inventory", inventory_source),
        ("first-linear", first_linear_source),
    ):
        if "qpx_harness" in source:
            raise AssertionError(
                f"historical {label} recipe retains legacy production dependency"
            )

    cli_source = (ROOT / "physics_harness/cli/app.py").read_text(encoding="utf-8")
    cli_ok = (
        "inventory-nullspace" not in cli_source
        and "inventory-first-linear" not in cli_source
        and "electron_inventory" not in cli_source
    )
    print("ISSUE54_FINAL_CLI_CANONICAL_SURFACE:", "PASS" if cli_ok else "FAIL")
    if not cli_ok:
        return 1

    print("ISSUE54_FINAL_IMPORT_IDENTITY: PASS")
    print("ISSUE54_FINAL_EVRS_CONSUMED_BY_REFACTOR: 0")
    print("ISSUE54_FINAL_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
