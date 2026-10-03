#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from physics_harness.adapters.moose import parameters as mp

CORE = Path(__file__).with_name("_enable_electric_feedback_core.py")


def _load_core():
    spec = importlib.util.spec_from_file_location("electric_feedback_core", CORE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load feedback core: {CORE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    core = _load_core()
    rc = core.main()
    if rc:
        return int(rc)
    if len(sys.argv) != 2:
        raise SystemExit("usage: enable_electric_feedback.py <case-dir>")

    case = Path(sys.argv[1]).resolve()
    input_path = case / "input.i"
    text = input_path.read_text()

    # Canonical positive energy state: drift transports exp(log_c_epsilon)
    # with the table-looked-up electron-energy mobility.
    text = mp.upsert_parameter(
        text,
        "FVKernels/energy_drift",
        "type",
        "PhysicsFVLogMolarElectrostaticDrift",
    )
    text = mp.upsert_parameter(
        text,
        "FVKernels/energy_drift",
        "variable",
        "log_c_epsilon",
    )
    input_path.write_text(text)

    contract_path = case / "electric_feedback_contract.json"
    contract = json.loads(contract_path.read_text())
    contract["electron_energy_state"] = "c_epsilon_molar = exp(log_c_epsilon)"
    contract["checks"]["electron_energy_drift_on"] = (
        mp.get_parameter(text, "FVKernels/energy_drift", "type")
        == "PhysicsFVLogMolarElectrostaticDrift"
        and mp.get_parameter(text, "FVKernels/energy_drift", "variable") == "log_c_epsilon"
        and mp.get_parameter(text, "FVKernels/energy_drift", "mobility")
        == "electron_energy_mobility"
        and mp.get_parameter(text, "FVKernels/energy_drift", "charge_number") == "-1"
    )
    contract["failed_checks"] = sorted(
        name for name, ok in contract["checks"].items() if not ok
    )
    contract["status"] = "PASS" if not contract["failed_checks"] else "FAIL"
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps(contract, indent=2, sort_keys=True))
    if contract["failed_checks"]:
        raise SystemExit(f"electric feedback contract failed: {contract['failed_checks']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
