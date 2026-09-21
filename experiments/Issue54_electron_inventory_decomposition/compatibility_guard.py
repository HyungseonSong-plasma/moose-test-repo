#!/usr/bin/env python3
"""Read-only guard for the historical Issue45 inventory contract after retirement."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.historical_recipe_support import issue45_inventory_constraint as inventory

EXPECTED_RECIPE_LITERALS = {
    "ISSUE": 45,
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
HISTORICAL_RUNTIME_CONTRACT = {"DT_REFERENCE": 1.0e-13, "STEPS": 1}

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
    "physics_harness/execution/cases.py",
    "physics_harness/evidence/identity.py",
)


def main() -> int:
    for name, expected in EXPECTED_RECIPE_LITERALS.items():
        observed = getattr(inventory, name)
        if observed != expected:
            raise AssertionError(
                f"historical scientific constant drift: {name} "
                f"expected={expected!r} observed={observed!r}"
            )
    assert HISTORICAL_RUNTIME_CONTRACT == {"DT_REFERENCE": 1.0e-13, "STEPS": 1}

    resurrected = [relative for relative in RETIRED_PATHS if (ROOT / relative).exists()]
    if resurrected:
        raise AssertionError(f"retired inventory production owner resurrected: {resurrected}")

    missing = [relative for relative in GENERIC_OWNER_FILES if not (ROOT / relative).is_file()]
    if missing:
        raise AssertionError(f"canonical generic mechanics missing: {missing}")

    source = Path(inventory.__file__).read_text(encoding="utf-8")
    for required in (
        "from physics_harness.adapters.moose import blocks as mb",
        "from physics_harness.adapters.moose import parameters as mp",
        "from physics_harness.adapters.moose.preflight import validate_parser_symbols_text",
    ):
        if required not in source:
            raise AssertionError(f"historical inventory recipe lost generic owner: {required}")
    if "qpx_harness" in source:
        raise AssertionError("historical inventory recipe still depends on legacy production namespace")

    print("ISSUE54_M1_SCIENTIFIC_CONSTANTS: PASS")
    print("ISSUE54_M1_GENERIC_MECHANICS: PASS")
    print("ISSUE54_M1_RETIRED_PRODUCTION_SURFACE: ABSENT")
    print("ISSUE54_M1_COMPATIBILITY_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
