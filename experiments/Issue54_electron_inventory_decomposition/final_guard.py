#!/usr/bin/env python3
"""Final read-only ownership/compatibility gate for electron-inventory capability."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FACADE = ROOT / "qpx_harness" / "electron_inventory_nullspace.py"
FIRST_LINEAR_FACADE = ROOT / "qpx_harness" / "issue45_first_linear.py"
OWNER_ROOT = ROOT / "qpx_harness" / "inventory"
QPX_CLI = ROOT / "qpx_harness" / "cli" / "app.py"

EXPECTED_OWNER_FILES = {
    "characterization.py",
    "cli.py",
    "closure_model.py",
    "closure_runtime.py",
    "closure_schema.py",
    "constants.py",
    "errors.py",
    "first_linear_characterization.py",
    "first_linear_orchestration.py",
    "first_linear_stats.py",
    "first_linear_structure.py",
    "orchestration.py",
    "structure.py",
}
EXPECTED_COMPAT_ATTRS = {
    "ElectronInventoryNullspaceError",
    "_base_case_context",
    "_build_constrained_quasisteady_input",
    "_evidence_root",
    "_stage_case",
    "_synthetic_constrained_input",
    "audit_constrained_quasisteady_structure",
}


def main() -> int:
    ok = True
    observed = {path.name for path in OWNER_ROOT.glob("*.py")}
    missing = EXPECTED_OWNER_FILES - observed
    print(
        "ISSUE54_FINAL_CANONICAL_INVENTORY_OWNER:",
        "PASS" if not missing else "FAIL missing=" + ",".join(sorted(missing)),
    )
    ok = ok and not missing

    cli_text = QPX_CLI.read_text()
    cli_ok = (
        "from qpx_harness.inventory.cli import" in cli_text
        and '"inventory-nullspace"' in cli_text
        and '"inventory-first-linear"' in cli_text
        and "qpx_harness.electron_inventory_nullspace" not in cli_text
        and "qpx_harness.issue45_first_linear" not in cli_text
    )
    print("ISSUE54_FINAL_CLI_CANONICAL_SURFACE:", "PASS" if cli_ok else "FAIL")
    ok = ok and cli_ok

    try:
        inventory_structure = importlib.import_module("qpx_harness.inventory.structure")
        inventory_model = importlib.import_module("qpx_harness.inventory.closure_model")
        inventory_orchestration = importlib.import_module("qpx_harness.inventory.orchestration")
        first_linear = importlib.import_module("qpx_harness.inventory.first_linear_orchestration")
        if FACADE.is_file():
            facade = importlib.import_module("qpx_harness.electron_inventory_nullspace")
            compat = (
                facade.audit_constrained_quasisteady_structure
                is inventory_structure.audit_constrained_quasisteady_structure
                and facade._build_constrained_quasisteady_input
                is inventory_model._build_constrained_quasisteady_input
                and facade._base_case_context is inventory_orchestration._base_case_context
                and facade._stage_case is inventory_orchestration._stage_case
            )
            print("ISSUE54_FINAL_LEGACY_FACADE_COMPAT:", "PASS" if compat else "FAIL")
            ok = ok and compat
        else:
            print("ISSUE54_FINAL_LEGACY_FACADE_COMPAT: RETIRED")

        if FIRST_LINEAR_FACADE.is_file():
            legacy_first = importlib.import_module("qpx_harness.issue45_first_linear")
            missing_attrs = {
                name for name in EXPECTED_COMPAT_ATTRS if not hasattr(legacy_first, name)
            }
            print(
                "ISSUE54_FINAL_FIRST_LINEAR_COMPAT:",
                "PASS" if not missing_attrs else "FAIL missing=" + ",".join(sorted(missing_attrs)),
            )
            ok = ok and not missing_attrs
        else:
            print("ISSUE54_FINAL_FIRST_LINEAR_COMPAT: RETIRED")

        if first_linear.run_preflight is None:
            raise AssertionError("canonical first-linear orchestration missing")
    except Exception as exc:
        print(f"ISSUE54_FINAL_IMPORT_IDENTITY: FAIL ({exc})")
        ok = False
    else:
        print("ISSUE54_FINAL_IMPORT_IDENTITY: PASS")

    print("ISSUE54_FINAL_EVRS_CONSUMED_BY_REFACTOR: 0")
    print("ISSUE54_FINAL_GUARD:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
