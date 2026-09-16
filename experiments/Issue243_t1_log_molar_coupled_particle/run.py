#!/usr/bin/env python3
"""Issue #243 T1: log-molar electron particle state in the accepted coupled child."""
from __future__ import annotations

import math
from typing import Any

from experiments.Issue217_sheath_energy_closure import run as w45
from experiments.Issue27_surface_reactions.controlled_wall import see as a8
from experiments.historical_recipe_support import issue26_energy_chain as energy
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

AVOGADRO = 6.02214076e23
LOG_E = "log_e"
PHYSICAL = "n_e_physical"
ENERGY_COMPAT = "issue243_energy_ne_hat_compat"


def _replace_top_level(text: str, name: str, value: str) -> str:
    import re
    pattern = rf"(?m)^(\s*{re.escape(name)}\s*=\s*)[^#\r\n]+"
    new, count = re.subn(pattern, rf"\g<1>{value}", text)
    if count != 1:
        raise RuntimeError(f"expected one top-level {name}, got {count}")
    return new


def build_t1_input() -> tuple[str, dict[str, Any]]:
    text, predecessor = w45.build_issue217_input()
    n_ref = float(predecessor["electron_reference_density_m3"])

    # Rename only the solved particle state. Energy stays n_epsilon in T1.
    if not mb.has_block(text, "Variables/n_e"):
        raise RuntimeError("accepted predecessor lacks Variables/n_e")
    text = mb.remove_block(text, "Variables/n_e")
    c0 = n_ref / AVOGADRO
    text = mb.insert_child_block(text, "Variables", f"""  [{LOG_E}]
    type = MooseVariableFVReal
    initial_condition = {math.log(c0):.17g}
    block = plasma
  []""")

    # Canonical physical bridge: no arbitrary reference density.
    text = mp.upsert_parameter(text, "FunctorMaterials/electron_density_physical", "functor_names", f"'{LOG_E}'")
    text = mp.upsert_parameter(text, "FunctorMaterials/electron_density_physical", "functor_symbols", "loge")
    text = mp.upsert_parameter(text, "FunctorMaterials/electron_density_physical", "expression", f"'{AVOGADRO:.17g}*exp(loge)'")

    # Particle transport: conservative N_A*exp(log_e) representation.
    text = mp.upsert_parameter(text, "FVKernels/n_e_time", "type", "PhysicsFVLogMolarElectronTimeDerivative")
    text = mp.upsert_parameter(text, "FVKernels/n_e_time", "variable", LOG_E)
    text = mp.upsert_parameter(text, "FVKernels/n_e_diffusion", "type", "PhysicsFVLogMolarElectronDiffusion")
    text = mp.upsert_parameter(text, "FVKernels/n_e_diffusion", "variable", LOG_E)
    text = mp.upsert_parameter(text, "FVKernels/n_e_drift", "type", "PhysicsFVLogMolarElectrostaticDrift")
    text = mp.upsert_parameter(text, "FVKernels/n_e_drift", "variable", LOG_E)

    # Canonical chemistry source remains physical number/m^3/s; source kernel now
    # enters it directly into the physical-number residual reconstructed from log_e.
    text = mp.upsert_parameter(text, "FVKernels/s5r_electron_source", "type", "PhysicsFVLogMolarElectronReactionSource")
    text = mp.upsert_parameter(text, "FVKernels/s5r_electron_source", "variable", LOG_E)
    text = mp.remove_parameter(text, "FVKernels/s5r_electron_source", "n_ref")

    # Primary sheath particle owner uses exactly the accepted suppression law but
    # reconstructs physical density from log_e. SEE is converted from normalized
    # particle flux to physical number flux by multiplying its existing functor by n_ref;
    # n_ref is not retained in the particle equation or SEE material expression.
    text = mp.upsert_parameter(text, f"FVBCs/{w45.PARTICLE_BC}", "variable", LOG_E)
    text = mp.upsert_parameter(text, f"FVBCs/{w45.PARTICLE_BC}", "log_molar_state", "true")
    see_expr = mp.get_parameter(text, f"FunctorMaterials/{a8.SEE_MATERIAL}", "expression") or ""
    see_expr = see_expr.strip("'")
    text = mp.upsert_parameter(text, f"FunctorMaterials/{a8.SEE_MATERIAL}", "expression", f"'{n_ref:.17g}*({see_expr})'")
    text = mp.upsert_parameter(text, f"FVBCs/{a8.SEE_BC}", "variable", LOG_E)

    # T1 freezes energy representation. Its existing mean-energy and primary-energy
    # wall owners require n_e/n_ref, so expose an explicitly energy-only compatibility
    # bridge. This is the sole allowed n_ref use and is removed in T2.
    mb.require_absent(text, f"FunctorMaterials/{ENERGY_COMPAT}")
    text = mb.insert_child_block(text, "FunctorMaterials", f"""  [{ENERGY_COMPAT}]
    type = ADParsedFunctorMaterial
    property_name = {ENERGY_COMPAT}
    functor_names = '{PHYSICAL}'
    functor_symbols = 'nephys'
    expression = 'nephys/{n_ref:.17g}'
    block = plasma
  []""")
    text = mp.upsert_parameter(text, "FunctorMaterials/s5r_mean_energy", "electron_density", ENERGY_COMPAT)
    text = mp.upsert_parameter(text, f"FVBCs/{w45.ENERGY_BC}", "electron_density", ENERGY_COMPAT)

    # Diagnostics formerly naming n_e are retargeted to physical density/log state.
    for pp in ("n_e_avg", "n_e_min", "n_e_max", "n_e_inventory"):
        if mb.has_block(text, f"Postprocessors/{pp}"):
            text = mp.upsert_parameter(text, f"Postprocessors/{pp}", "functor", PHYSICAL)

    # T0 established representation-dependent automatic scaling as a false
    # discriminator. Keep scaling explicit/off for T1 qualification.
    text = mp.upsert_parameter(text, "Executioner", "automatic_scaling", "false")

    return text, {
        **predecessor,
        "issue": 243,
        "claim": "t1_coupled_log_molar_particle_no_particle_nref",
        "electron_solver_unknown": LOG_E,
        "electron_physical_density": f"{PHYSICAL}=N_A*exp({LOG_E})",
        "particle_reference_density_removed": True,
        "energy_representation_frozen": True,
        "energy_only_compatibility_bridge": ENERGY_COMPAT,
    }


def audit_t1_input(text: str) -> dict[str, Any]:
    particle_paths = (
        "FVKernels/n_e_time", "FVKernels/n_e_diffusion", "FVKernels/n_e_drift",
        "FVKernels/s5r_electron_source", f"FVBCs/{w45.PARTICLE_BC}",
        f"FunctorMaterials/{a8.SEE_MATERIAL}", f"FVBCs/{a8.SEE_BC}",
        "FunctorMaterials/electron_density_physical",
    )
    checks = {
        "log_state_present": mb.has_block(text, f"Variables/{LOG_E}"),
        "old_particle_state_absent": not mb.has_block(text, "Variables/n_e"),
        "physical_bridge_exact": mp.get_parameter(text, "FunctorMaterials/electron_density_physical", "expression") == f"'{AVOGADRO:.17g}*exp(loge)'",
        "poisson_uses_physical_bridge": mp.get_parameter(text, "FunctorMaterials/r31_charge_density", "electron_density") == PHYSICAL,
        "particle_time_log": mp.get_parameter(text, "FVKernels/n_e_time", "type") == "PhysicsFVLogMolarElectronTimeDerivative" and mp.get_parameter(text, "FVKernels/n_e_time", "variable") == LOG_E,
        "particle_diffusion_log": mp.get_parameter(text, "FVKernels/n_e_diffusion", "type") == "PhysicsFVLogMolarElectronDiffusion" and mp.get_parameter(text, "FVKernels/n_e_diffusion", "variable") == LOG_E,
        "particle_drift_log": mp.get_parameter(text, "FVKernels/n_e_drift", "type") == "PhysicsFVLogMolarElectrostaticDrift" and mp.get_parameter(text, "FVKernels/n_e_drift", "variable") == LOG_E,
        "particle_source_no_nref": mp.get_parameter(text, "FVKernels/s5r_electron_source", "type") == "PhysicsFVLogMolarElectronReactionSource" and mp.get_parameter(text, "FVKernels/s5r_electron_source", "n_ref") is None,
        "primary_sheath_log": mp.get_parameter(text, f"FVBCs/{w45.PARTICLE_BC}", "variable") == LOG_E and mp.get_parameter(text, f"FVBCs/{w45.PARTICLE_BC}", "log_molar_state") == "true",
        "see_log": mp.get_parameter(text, f"FVBCs/{a8.SEE_BC}", "variable") == LOG_E,
        "energy_state_unchanged": mb.has_block(text, "Variables/n_epsilon"),
        "energy_compat_present": mb.has_block(text, f"FunctorMaterials/{ENERGY_COMPAT}"),
        "mean_energy_uses_energy_compat": mp.get_parameter(text, "FunctorMaterials/s5r_mean_energy", "electron_density") == ENERGY_COMPAT,
        "energy_wall_uses_energy_compat": mp.get_parameter(text, f"FVBCs/{w45.ENERGY_BC}", "electron_density") == ENERGY_COMPAT,
        "automatic_scaling_off": mp.get_parameter(text, "Executioner", "automatic_scaling") == "false",
    }
    checks["particle_paths_no_n_ref_token"] = all("n_ref" not in (mp.get_block(text, p) or "") for p in particle_paths)
    failed = sorted(k for k, ok in checks.items() if not ok)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def self_test() -> int:
    text, _ = build_t1_input()
    audit = audit_t1_input(text)
    if audit["status"] != "PASS":
        raise RuntimeError(audit)
    print("Issue243 T1 static audit PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
