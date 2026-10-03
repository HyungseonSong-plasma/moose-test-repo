#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp


def add_child(text: str, parent: str, name: str, raw: str) -> str:
    path = f"{parent}/{name}"
    if mb.has_block(text, path):
        raise RuntimeError(f"log-energy block already exists: {path}")
    return mb.insert_child_block(text, parent, raw)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: log_energy_state.py <case-dir>")

    case = Path(sys.argv[1]).resolve()
    input_path = case / "input.i"
    if not input_path.is_file():
        raise RuntimeError(f"missing generated monolithic input: {input_path}")

    text = input_path.read_text()
    if not mb.has_block(text, "Variables/c_epsilon"):
        raise RuntimeError("expected linear Variables/c_epsilon before log-state conversion")
    if mb.has_block(text, "Variables/log_c_epsilon"):
        raise RuntimeError("Variables/log_c_epsilon already exists")

    c_eps0_raw = mp.get_parameter(text, "Variables/c_epsilon", "initial_condition")
    if c_eps0_raw is None:
        raise RuntimeError("Variables/c_epsilon is missing initial_condition")
    c_eps0 = float(c_eps0_raw)
    if not math.isfinite(c_eps0) or c_eps0 <= 0.0:
        raise RuntimeError(f"c_epsilon initial condition must be positive, got {c_eps0}")

    # Solve ell_epsilon = log(c_epsilon) while retaining the conservative
    # c_epsilon equation.  Every transport kernel reconstructs exp(ell_epsilon),
    # so positivity is guaranteed for every Newton trial state.
    text = mb.remove_block(text, "Variables/c_epsilon")
    text = add_child(
        text,
        "Variables",
        "log_c_epsilon",
        f"""  [log_c_epsilon]
    type = MooseVariableFVReal
    # c_epsilon = exp(log_c_epsilon) [eV mol/m^3]
    initial_condition = {math.log(c_eps0):.17g}
    block = plasma
  []""",
    )

    text = add_child(
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

    # Closure sees the reconstructed positive physical energy density.
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/electron_energy_density",
        "functor_names",
        "'c_epsilon_molar'",
    )

    # Conservative time derivative and diffusion of exp(log_c_epsilon).
    text = mp.upsert_parameter(
        text, "FVKernels/energy_time", "type", "PhysicsFVLogMolarElectronTimeDerivative"
    )
    text = mp.upsert_parameter(
        text, "FVKernels/energy_time", "variable", "log_c_epsilon"
    )
    text = mp.upsert_parameter(
        text, "FVKernels/energy_diffusion", "type", "PhysicsFVLogMolarElectronDiffusion"
    )
    text = mp.upsert_parameter(
        text, "FVKernels/energy_diffusion", "variable", "log_c_epsilon"
    )
    text = mp.upsert_parameter(
        text, "FVKernels/energy_diffusion", "coeff_interp_method", "harmonic"
    )

    # If live electric feedback has already inserted energy drift, preserve it
    # consistently in the same positive log-state representation.
    if mb.has_block(text, "FVKernels/energy_drift"):
        text = mp.upsert_parameter(
            text,
            "FVKernels/energy_drift",
            "type",
            "PhysicsFVLogMolarElectrostaticDrift",
        )
        text = mp.upsert_parameter(
            text, "FVKernels/energy_drift", "variable", "log_c_epsilon"
        )

    # The BC contributes the physical conservative energy flux directly to
    # F(exp(log_c_epsilon)) = 0; no chain-rule multiplier belongs in the residual.
    text = mp.upsert_parameter(
        text,
        "FVBCs/electron_energy_thermal_wall_loss",
        "variable",
        "log_c_epsilon",
    )

    text = mp.upsert_parameter(
        text,
        "Postprocessors/electron_energy_inventory_eV_mol",
        "functor",
        "c_epsilon_molar",
    )

    checks = {
        "linear_energy_variable_removed": not mb.has_block(text, "Variables/c_epsilon"),
        "log_energy_variable_present": mb.has_block(text, "Variables/log_c_epsilon"),
        "positive_energy_reconstruction_present": (
            mb.has_block(text, "FunctorMaterials/electron_energy_molar")
            and mp.get_parameter(
                text, "FunctorMaterials/electron_energy_molar", "property_name"
            ) == "c_epsilon_molar"
        ),
        "closure_reads_positive_energy": (
            mp.get_parameter(
                text, "FunctorMaterials/electron_energy_density", "functor_names"
            ) == "'c_epsilon_molar'"
        ),
        "energy_time_is_log_conservative": (
            mp.get_parameter(text, "FVKernels/energy_time", "type")
            == "PhysicsFVLogMolarElectronTimeDerivative"
            and mp.get_parameter(text, "FVKernels/energy_time", "variable")
            == "log_c_epsilon"
        ),
        "energy_diffusion_is_log_conservative": (
            mp.get_parameter(text, "FVKernels/energy_diffusion", "type")
            == "PhysicsFVLogMolarElectronDiffusion"
            and mp.get_parameter(text, "FVKernels/energy_diffusion", "variable")
            == "log_c_epsilon"
        ),
        "energy_drift_is_log_conservative": (
            not mb.has_block(text, "FVKernels/energy_drift")
            or (
                mp.get_parameter(text, "FVKernels/energy_drift", "type")
                == "PhysicsFVLogMolarElectrostaticDrift"
                and mp.get_parameter(text, "FVKernels/energy_drift", "variable")
                == "log_c_epsilon"
            )
        ),
        "energy_wall_flux_attached_to_log_state": (
            mp.get_parameter(
                text, "FVBCs/electron_energy_thermal_wall_loss", "variable"
            ) == "log_c_epsilon"
        ),
        "energy_inventory_uses_reconstruction": (
            mp.get_parameter(
                text, "Postprocessors/electron_energy_inventory_eV_mol", "functor"
            ) == "c_epsilon_molar"
        ),
        "no_linear_energy_kernel_variable_reference": (
            re.search(r"(?m)^\s*variable\s*=\s*c_epsilon\s*$", text) is None
        ),
    }

    failed = sorted(name for name, ok in checks.items() if not ok)
    contract = {
        "model": "positive-log-electron-energy-state",
        "solved_variable": "log_c_epsilon",
        "conserved_state": "c_epsilon_molar = exp(log_c_epsilon)",
        "conserved_state_unit": "eV mol/m^3",
        "initial_c_epsilon_eV_mol_m3": c_eps0,
        "initial_log_c_epsilon": math.log(c_eps0),
        "positivity": "guaranteed by exponential reconstruction for every nonlinear trial state",
        "checks": checks,
        "failed_checks": failed,
        "status": "PASS" if not failed else "FAIL",
    }

    input_path.write_text(text)
    (case / "log_energy_state_contract.json").write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(contract, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(f"log energy state contract failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
