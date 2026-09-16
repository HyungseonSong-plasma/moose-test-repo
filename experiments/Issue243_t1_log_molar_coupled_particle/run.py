#!/usr/bin/env python3
"""Issue #243 T1: log-molar electron particle state in the accepted coupled child."""
from __future__ import annotations

import math
import re
from typing import Any

from experiments.Issue217_sheath_energy_closure import run as w45
from experiments.Issue27_surface_reactions.controlled_wall import see as a8
from experiments.historical_recipe_support import issue26_energy_chain as energy
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose.input import MooseInput

AVOGADRO = 6.02214076e23
LOG_E = "log_e"
PHYSICAL = "n_e_physical"
ENERGY_COMPAT = "issue243_energy_ne_hat_compat"
PHYSICAL_SEE_MATERIAL = "issue243_see_physical_particle_material"
PHYSICAL_SEE_FUNCTOR = "issue243_see_physical_particle_flux_inward"


def _block_text(text: str, path: str) -> str:
    span = MooseInput(text).unique(path)
    return text[span.start:span.end]


def _remove_root_parameter(text: str, name: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(name)}\s*=\s*[^#\r\n]*(?:\s*#.*)?(?:\r?\n|$)")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one root parameter {name}, found {len(matches)}")
    out = pattern.sub("", text, count=1)
    MooseInput(out)
    return out


def build_t1_input() -> tuple[str, dict[str, Any]]:
    text, predecessor = w45.build_issue217_input()
    n_ref = float(predecessor["electron_reference_density_m3"])
    text = _remove_root_parameter(text, "n_e_value")
    if not mb.has_block(text, "Variables/n_e"):
        raise RuntimeError("accepted predecessor lacks Variables/n_e")
    text = mb.remove_block(text, "Variables/n_e")
    c0 = n_ref / AVOGADRO
    text = mb.insert_child_block(text, "Variables", f"""  [{LOG_E}]
    type = MooseVariableFVReal
    initial_condition = {math.log(c0):.17g}
    block = plasma
  []""")

    text = mp.upsert_parameter(text, "FunctorMaterials/electron_density_physical", "functor_names", f"'{LOG_E}'")
    text = mp.upsert_parameter(text, "FunctorMaterials/electron_density_physical", "functor_symbols", "loge")
    text = mp.upsert_parameter(text, "FunctorMaterials/electron_density_physical", "expression", f"'{AVOGADRO:.17g}*exp(loge)'")

    text = mp.upsert_parameter(text, "FVKernels/n_e_time", "type", "PhysicsFVLogMolarElectronTimeDerivative")
    text = mp.upsert_parameter(text, "FVKernels/n_e_time", "variable", LOG_E)
    text = mp.upsert_parameter(text, "FVKernels/n_e_diffusion", "type", "PhysicsFVLogMolarElectronDiffusion")
    text = mp.upsert_parameter(text, "FVKernels/n_e_diffusion", "variable", LOG_E)
    text = mp.upsert_parameter(text, "FVKernels/n_e_drift", "type", "PhysicsFVLogMolarElectrostaticDrift")
    text = mp.upsert_parameter(text, "FVKernels/n_e_drift", "variable", LOG_E)

    text = mp.upsert_parameter(text, "FVKernels/s5r_electron_source", "type", "PhysicsFVLogMolarElectronReactionSource")
    text = mp.upsert_parameter(text, "FVKernels/s5r_electron_source", "variable", LOG_E)
    text = mp.remove_parameter(text, "FVKernels/s5r_electron_source", "n_ref")

    text = mp.upsert_parameter(text, f"FVBCs/{w45.PARTICLE_BC}", "variable", LOG_E)
    text = mp.upsert_parameter(text, f"FVBCs/{w45.PARTICLE_BC}", "log_molar_state", "true")

    mb.require_absent(text, f"FunctorMaterials/{PHYSICAL_SEE_MATERIAL}")
    gamma = 0.05
    physical_see_expression = (
        f"{gamma:.17g}*("
        f"(o2ps+o2pm)/{a8.M_O2_KG_PER_MOL:.17g}+"
        f"(ops+opm)/{a8.M_O_KG_PER_MOL:.17g})"
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{PHYSICAL_SEE_MATERIAL}]
    type = ADParsedFunctorMaterial
    property_name = {PHYSICAL_SEE_FUNCTOR}
    functor_names = 'ion_surface_mass_flux_O2p ion_migration_mass_flux_O2p ion_surface_mass_flux_Op ion_migration_mass_flux_Op'
    functor_symbols = 'o2ps o2pm ops opm'
    expression = '{physical_see_expression}'
    block = plasma
  []""",
    )
    text = mp.upsert_parameter(text, f"FVBCs/{a8.SEE_BC}", "variable", LOG_E)
    text = mp.upsert_parameter(text, f"FVBCs/{a8.SEE_BC}", "functor", PHYSICAL_SEE_FUNCTOR)

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

    for pp in ("n_e_avg", "n_e_min", "n_e_max", "n_e_inventory"):
        if mb.has_block(text, f"Postprocessors/{pp}"):
            text = mp.upsert_parameter(text, f"Postprocessors/{pp}", "functor", PHYSICAL)
    text = mp.upsert_parameter(text, "Executioner", "automatic_scaling", "true")

    return text, {
        **predecessor,
        "issue": 243,
        "claim": "t1_coupled_log_molar_particle_no_particle_nref",
        "electron_solver_unknown": LOG_E,
        "electron_physical_density": f"{PHYSICAL}=N_A*exp({LOG_E})",
        "particle_reference_density_removed": True,
        "energy_representation_frozen": True,
        "energy_only_compatibility_bridge": ENERGY_COMPAT,
        "particle_see_functor": PHYSICAL_SEE_FUNCTOR,
        "energy_see_functor_preserved": a8.SEE_FUNCTOR,
    }


def audit_t1_input(text: str) -> dict[str, Any]:
    particle_paths = (
        "FVKernels/n_e_time", "FVKernels/n_e_diffusion", "FVKernels/n_e_drift",
        "FVKernels/s5r_electron_source", f"FVBCs/{w45.PARTICLE_BC}",
        f"FunctorMaterials/{PHYSICAL_SEE_MATERIAL}", f"FVBCs/{a8.SEE_BC}",
        "FunctorMaterials/electron_density_physical",
    )
    checks = {
        "legacy_root_n_e_value_absent": re.search(r"(?m)^n_e_value\s*=", text) is None,
        "log_state_present": mb.has_block(text, f"Variables/{LOG_E}"),
        "old_particle_state_absent": not mb.has_block(text, "Variables/n_e"),
        "physical_bridge_exact": mp.get_parameter(text, "FunctorMaterials/electron_density_physical", "expression") == f"'{AVOGADRO:.17g}*exp(loge)'",
        "poisson_uses_physical_bridge": mp.get_parameter(text, "FunctorMaterials/r31_charge_density", "electron_density") == PHYSICAL,
        "particle_time_log": mp.get_parameter(text, "FVKernels/n_e_time", "type") == "PhysicsFVLogMolarElectronTimeDerivative" and mp.get_parameter(text, "FVKernels/n_e_time", "variable") == LOG_E,
        "particle_diffusion_log": mp.get_parameter(text, "FVKernels/n_e_diffusion", "type") == "PhysicsFVLogMolarElectronDiffusion" and mp.get_parameter(text, "FVKernels/n_e_diffusion", "variable") == LOG_E,
        "particle_drift_log": mp.get_parameter(text, "FVKernels/n_e_drift", "type") == "PhysicsFVLogMolarElectrostaticDrift" and mp.get_parameter(text, "FVKernels/n_e_drift", "variable") == LOG_E,
        "particle_source_no_nref": mp.get_parameter(text, "FVKernels/s5r_electron_source", "type") == "PhysicsFVLogMolarElectronReactionSource" and mp.get_parameter(text, "FVKernels/s5r_electron_source", "n_ref") is None,
        "primary_sheath_log": mp.get_parameter(text, f"FVBCs/{w45.PARTICLE_BC}", "variable") == LOG_E and mp.get_parameter(text, f"FVBCs/{w45.PARTICLE_BC}", "log_molar_state") == "true",
        "particle_see_log": mp.get_parameter(text, f"FVBCs/{a8.SEE_BC}", "variable") == LOG_E,
        "particle_see_uses_molar_functor": mp.get_parameter(text, f"FVBCs/{a8.SEE_BC}", "functor") == PHYSICAL_SEE_FUNCTOR and f"{AVOGADRO:.17g}" not in _block_text(text, f"FunctorMaterials/{PHYSICAL_SEE_MATERIAL}"),
        "physical_see_material_present": mb.has_block(text, f"FunctorMaterials/{PHYSICAL_SEE_MATERIAL}"),
        "energy_see_uses_original_normalized_functor": a8.SEE_FUNCTOR in mp.words(mp.get_parameter(text, f"FunctorMaterials/{energy.SEE_ENERGY_MATERIAL}", "functor_names")),
        "energy_state_unchanged": mb.has_block(text, "Variables/n_epsilon"),
        "energy_compat_present": mb.has_block(text, f"FunctorMaterials/{ENERGY_COMPAT}"),
        "mean_energy_uses_energy_compat": mp.get_parameter(text, "FunctorMaterials/s5r_mean_energy", "electron_density") == ENERGY_COMPAT,
        "energy_wall_uses_energy_compat": mp.get_parameter(text, f"FVBCs/{w45.ENERGY_BC}", "electron_density") == ENERGY_COMPAT,
        "automatic_scaling_on": mp.get_parameter(text, "Executioner", "automatic_scaling") == "true",
    }
    checks["particle_paths_no_n_ref_token"] = all("n_ref" not in _block_text(text, p) for p in particle_paths)
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