#!/usr/bin/env python3
"""Read-only compatibility guard for the canonical inventory capability.

Historical facades may exist during migration, but the scientific constants,
CLI behavior, and callable surface are owned by qpx_harness.inventory.
No QPX scientific runtime is invoked.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OWNER_ROOT = ROOT / "qpx_harness" / "inventory"
FACADE = ROOT / "qpx_harness" / "electron_inventory_nullspace.py"
FIRST_LINEAR = ROOT / "qpx_harness" / "issue45_first_linear.py"
QPX_CLI = ROOT / "qpx_harness" / "cli" / "app.py"

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
    try:
        constants = importlib.import_module("qpx_harness.inventory.constants")
        for name, expected in EXPECTED_LITERALS.items():
            observed = getattr(constants, name)
            if observed != expected:
                raise AssertionError(
                    f"scientific constant drift: {name} expected={expected!r} observed={observed!r}"
                )

        cli = importlib.import_module("qpx_harness.inventory.cli")
        if not callable(cli.inventory_main) or not callable(cli.first_linear_main):
            raise AssertionError("canonical inventory CLI entrypoints missing")
        cli_source = QPX_CLI.read_text()
        if (
            "from qpx_harness.inventory.cli import" not in cli_source
            or "qpx_harness.electron_inventory_nullspace" in cli_source
            or "qpx_harness.issue45_first_linear" in cli_source
        ):
            raise AssertionError("unified CLI is not cut over to canonical inventory")

        if FACADE.is_file():
            legacy = importlib.import_module("qpx_harness.electron_inventory_nullspace")
            missing = {name for name in EXPECTED_COMPAT_ATTRS if not hasattr(legacy, name)}
            if missing:
                raise AssertionError(f"legacy inventory facade drift: {sorted(missing)}")
        if FIRST_LINEAR.is_file():
            legacy_first = importlib.import_module("qpx_harness.issue45_first_linear")
            missing = {name for name in EXPECTED_COMPAT_ATTRS if not hasattr(legacy_first, name)}
            if missing:
                raise AssertionError(f"legacy first-linear facade drift: {sorted(missing)}")

        required_files = {
            "closure_model.py",
            "closure_runtime.py",
            "closure_schema.py",
            "constants.py",
            "first_linear_orchestration.py",
            "first_linear_structure.py",
            "orchestration.py",
            "structure.py",
        }
        observed = {path.name for path in OWNER_ROOT.glob("*.py")}
        missing_files = required_files - observed
        if missing_files:
            raise AssertionError(f"canonical inventory owners missing: {sorted(missing_files)}")

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
