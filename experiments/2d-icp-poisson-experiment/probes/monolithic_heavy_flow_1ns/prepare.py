#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from pathlib import Path

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

CORE = Path(__file__).with_name("_prepare_monolithic_core.py")


def _load_core():
    spec = importlib.util.spec_from_file_location("monolithic_prepare_core", CORE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load prepare core: {CORE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _add_child(text: str, parent: str, name: str, raw: str) -> str:
    path = f"{parent}/{name}"
    if mb.has_block(text, path):
        raise RuntimeError(f"canonical log-energy block already exists: {path}")
    return mb.insert_child_block(text, parent, raw)


def _canonicalize_log_energy(case: Path) -> None:
    input_path = case / "input.i"
    text = input_path.read_text()

    if not mb.has_block(text, "Variables/c_epsilon"):
        raise RuntimeError("prepare core did not produce Variables/c_epsilon")
    if mb.has_block(text, "Variables/log_c_epsilon"):
        raise RuntimeError("Variables/log_c_epsilon unexpectedly already exists")

    c_eps0_raw = mp.get_parameter(text, "Variables/c_epsilon", "initial_condition")
    if c_eps0_raw is None:
        raise RuntimeError("Variables/c_epsilon is missing initial_condition")
    c_eps0 = float(c_eps0_raw)
    if not math.isfinite(c_eps0) or c_eps0 <= 0.0:
        raise RuntimeError(f"electron energy initial condition must be positive, got {c_eps0}")

    text = mb.remove_block(text, "Variables/c_epsilon")
    text = _add_child(
        text,
        "Variables",
        "log_c_epsilon",
        f"""  [log_c_epsilon]
    type = MooseVariableFVReal
    # Conservative state: c_epsilon = exp(log_c_epsilon) [eV mol/m^3]
    initial_condition = {math.log(c_eps0):.17g}
    block = plasma
  []""",
    )

    text = _add_child(
        text,
        "FunctorMaterials",
        "electron_energy_molar",
        """  [electron_energy_molar]
    type = ADParsedFunctorMaterial
    property_name = c_epsilon_molar
    functor_names = 'log_c_epsilon'
    functor_symbols = 'leps'
    expression = 'exp(leps)'
    block = plasma
  []""",
    )

    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/electron_energy_density",
        "functor_names",
        "'c_epsilon_molar'",
    )
    text = mp.upsert_parameter(
        text, "FVKernels/energy_time", "type", "PhysicsFVLogMolarElectronTimeDerivative"
    )
    text = mp.upsert_parameter(text, "FVKernels/energy_time", "variable", "log_c_epsilon")
    text = mp.upsert_parameter(
        text, "FVKernels/energy_diffusion", "type", "PhysicsFVLogMolarElectronDiffusion"
    )
    text = mp.upsert_parameter(text, "FVKernels/energy_diffusion", "variable", "log_c_epsilon")
    text = mp.upsert_parameter(
        text, "FVKernels/energy_diffusion", "coeff_interp_method", "harmonic"
    )
    text = mp.upsert_parameter(
        text, "FVBCs/electron_energy_thermal_wall_loss", "variable", "log_c_epsilon"
    )
    text = mp.upsert_parameter(
        text,
        "Postprocessors/electron_energy_inventory_eV_mol",
        "functor",
        "c_epsilon_molar",
    )

    profile = mp.words(mp.get_parameter(text, "VectorPostprocessors/final_profile", "variable") or "")
    profile = [name for name in profile if name != "c_epsilon"]
    text = mp.upsert_parameter(
        text,
        "VectorPostprocessors/final_profile",
        "variable",
        "'" + " ".join(profile) + "'",
    )

    checks = {
        "linear_energy_variable_removed": not mb.has_block(text, "Variables/c_epsilon"),
        "log_energy_variable_present": mb.has_block(text, "Variables/log_c_epsilon"),
        "positive_energy_reconstruction_present": (
            mb.has_block(text, "FunctorMaterials/electron_energy_molar")
            and mp.get_parameter(text, "FunctorMaterials/electron_energy_molar", "property_name")
            == "c_epsilon_molar"
        ),
        "closure_reads_reconstructed_energy": (
            mp.get_parameter(text, "FunctorMaterials/electron_energy_density", "functor_names")
            == "'c_epsilon_molar'"
        ),
        "energy_time_log_conservative": (
            mp.get_parameter(text, "FVKernels/energy_time", "type")
            == "PhysicsFVLogMolarElectronTimeDerivative"
            and mp.get_parameter(text, "FVKernels/energy_time", "variable") == "log_c_epsilon"
        ),
        "energy_diffusion_log_conservative": (
            mp.get_parameter(text, "FVKernels/energy_diffusion", "type")
            == "PhysicsFVLogMolarElectronDiffusion"
            and mp.get_parameter(text, "FVKernels/energy_diffusion", "variable")
            == "log_c_epsilon"
        ),
        "energy_wall_flux_on_log_state": (
            mp.get_parameter(text, "FVBCs/electron_energy_thermal_wall_loss", "variable")
            == "log_c_epsilon"
        ),
        "energy_inventory_reconstructed": (
            mp.get_parameter(text, "Postprocessors/electron_energy_inventory_eV_mol", "functor")
            == "c_epsilon_molar"
        ),
        "no_linear_energy_kernel_reference": (
            re.search(r"(?m)^\s*variable\s*=\s*c_epsilon\s*$", text) is None
        ),
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    if failed:
        raise RuntimeError(f"canonical log-energy conversion failed: {failed}")

    input_path.write_text(text)

    contract_path = case / "probe_contract.json"
    contract = json.loads(contract_path.read_text())
    contract["electron_energy_state"] = {
        "solved_variable": "log_c_epsilon",
        "conserved_state": "c_epsilon_molar = exp(log_c_epsilon)",
        "unit": "eV mol/m^3",
        "positivity": "positive-by-construction",
    }
    contract["checks"].update(checks)
    contract["checks"]["all_monolithic_variables_present"] = all(
        mb.has_block(text, f"Variables/{name}")
        for name in {
            "u", "v", "p", "w_O2s", "w_O2p", "w_O", "w_Om", "w_Op", "w_Os",
            "log_e", "log_c_epsilon", "phi",
        }
    )
    contract["failed_checks"] = sorted(
        name for name, ok in contract["checks"].items() if not ok
    )
    contract["status"] = "PASS" if not contract["failed_checks"] else "FAIL"
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    if contract["failed_checks"]:
        raise RuntimeError(f"canonical probe contract failed: {contract['failed_checks']}")


def main() -> int:
    core = _load_core()
    rc = core.main()
    if rc:
        return int(rc)
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare.py <case-dir>")
    case = Path(sys.argv[1]).resolve()
    _canonicalize_log_energy(case)
    print(json.dumps(json.loads((case / "probe_contract.json").read_text()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
