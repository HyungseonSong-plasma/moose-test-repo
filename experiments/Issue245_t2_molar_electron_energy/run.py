#!/usr/bin/env python3
"""Issue #245 T2: conservative molar electron-energy state on the accepted T1 child."""
from __future__ import annotations

import math
from typing import Any

from experiments.Issue217_sheath_energy_closure import run as w45
from experiments.Issue243_t1_log_molar_coupled_particle import run as t1
from experiments.historical_recipe_support import issue192_s5r as s5
from experiments.historical_recipe_support import issue26_energy_chain as energy
from experiments.historical_recipe_support.issue26_e1 import ENERGY_REFERENCE_EV
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose.input import MooseInput

AVOGADRO = 6.02214076e23
ELEMENTARY_CHARGE_C = 1.602176634e-19
C_EPSILON = "c_epsilon"
C_E_MOLAR = "issue245_c_e_molar"
ENERGY_DENSITY_J = "issue245_electron_energy_density_J_m3"
ENERGY_INVENTORY_J = "issue245_electron_energy_inventory_J"
C_EPSILON_MIN = "issue245_c_epsilon_min"


def _block_text(text: str, path: str) -> str:
    span = MooseInput(text).unique(path)
    return text[span.start:span.end]


def _replace_block(text: str, path: str, parent: str, body: str) -> str:
    if not mb.has_block(text, path):
        raise RuntimeError(f"missing required predecessor block {path}")
    text = mb.remove_block(text, path)
    return mb.insert_child_block(text, parent, body)


def _elastic_expression(*, target_molar_mass_kg_per_mol: float, progress: str) -> str:
    particle_mass_kg = target_molar_mass_kg_per_mol / AVOGADRO
    exchange_factor = 3.0 * s5.ELECTRON_MASS_KG / particle_mass_kg
    return (
        f"'-{exchange_factor:.17g}*(0.66666666666666663*meanE-"
        f"{s5.K_B_OVER_E_EV_PER_K:.17g}*tgas)*rprog'"
    )


def build_t2_input() -> tuple[str, dict[str, Any]]:
    text, predecessor = t1.build_t1_input()
    t1_audit = t1.audit_t1_input(text)
    if t1_audit["status"] != "PASS":
        raise RuntimeError(f"T1 predecessor audit failed: {t1_audit['failed_checks']}")

    log0_text = mp.get_parameter(text, f"Variables/{t1.LOG_E}", "initial_condition")
    if log0_text is None:
        raise RuntimeError("T1 log_e initial condition is missing")
    c_e0 = math.exp(float(log0_text))
    c_epsilon0 = c_e0 * ENERGY_REFERENCE_EV

    # Replace only the solved energy representation. The accepted T1 particle
    # state and all heavy/Poisson ownership remain untouched.
    if not mb.has_block(text, "Variables/n_epsilon"):
        raise RuntimeError("T1 predecessor lacks Variables/n_epsilon")
    text = mb.remove_block(text, "Variables/n_epsilon")
    text = mb.insert_child_block(
        text,
        "Variables",
        f"""  [{C_EPSILON}]
    type = MooseVariableFVReal
    initial_condition = {c_epsilon0:.17g}
    block = plasma
  []""",
    )

    mb.require_absent(text, f"FunctorMaterials/{C_E_MOLAR}")
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{C_E_MOLAR}]
    type = ADParsedFunctorMaterial
    property_name = {C_E_MOLAR}
    functor_names = '{t1.LOG_E}'
    functor_symbols = 'loge'
    expression = 'exp(loge)'
    block = plasma
  []""",
    )

    text = _replace_block(
        text,
        "FunctorMaterials/s5r_mean_energy",
        "FunctorMaterials",
        f"""  [s5r_mean_energy]
    type = ADParsedFunctorMaterial
    property_name = mean_en_solved
    functor_names = '{C_EPSILON} {C_E_MOLAR}'
    functor_symbols = 'ceps ce'
    expression = 'ceps/ce'
    block = plasma
  []""",
    )

    # Conservative transport operators are representation-linear: after the
    # variable substitution their coefficients/topology remain identical.
    for path in (
        "FVKernels/s5r_n_epsilon_time",
        "FVKernels/s5r_n_epsilon_diffusion",
        "FVKernels/s5r_n_epsilon_drift",
    ):
        text = mp.upsert_parameter(text, path, "variable", C_EPSILON)

    # Elastic exchange: predecessor progress is mol/(m^3 s). The T2 source is
    # therefore energy[eV] * progress directly, with no N_A/(n_ref*eps_ref).
    for suffix, mass, channel in (
        ("ei02", s5.M_O2, "EI02"),
        ("ei17", s5.M_O, "EI17"),
    ):
        path = f"FunctorMaterials/s5r_{suffix}_elastic_energy"
        text = mp.upsert_parameter(
            text,
            path,
            "expression",
            _elastic_expression(
                target_molar_mass_kg_per_mol=mass,
                progress=s5.PROGRESS[channel],
            ),
        )
        text = mp.upsert_parameter(
            text, f"FVKernels/s5r_{suffix}_elastic_energy", "variable", C_EPSILON
        )

    # Inelastic electron-energy loss: reaction progress is mol/(m^3 s), so the
    # conservative molar-energy source coefficient is simply -DeltaE[eV].
    for channel, loss_eV in s5.ENERGY_LOSS_EV.items():
        path = f"FVKernels/s5r_energy_{channel.lower()}"
        text = mp.upsert_parameter(text, path, "variable", C_EPSILON)
        text = mp.upsert_parameter(text, path, "coef", f"{-loss_eV:.17g}")

    # Primary grounded-wall energy loss in eV mol/(m^2 s).
    energy_bc = f"FVBCs/{w45.ENERGY_BC}"
    text = mp.upsert_parameter(text, energy_bc, "variable", C_EPSILON)
    text = mp.upsert_parameter(text, energy_bc, "electron_density", C_E_MOLAR)
    text = mp.upsert_parameter(text, energy_bc, "molar_energy_state", "true")
    text = mp.remove_parameter(text, energy_bc, "energy_reference_eV")

    # SEE particle flux is already molar after T1. Inject exactly 4 eV per
    # emitted electron into c_epsilon, again without a normalization scale.
    see_material = f"FunctorMaterials/{energy.SEE_ENERGY_MATERIAL}"
    text = mp.upsert_parameter(
        text, see_material, "functor_names", f"'{t1.PHYSICAL_SEE_FUNCTOR}'"
    )
    text = mp.upsert_parameter(text, see_material, "functor_symbols", "'see_molar'")
    text = mp.upsert_parameter(text, see_material, "expression", "'4*see_molar'")
    text = mp.upsert_parameter(
        text, f"FVBCs/{energy.SEE_ENERGY_BC}", "variable", C_EPSILON
    )

    # Raw energy wall integrals are now eV mol/s. Convert to W only at the
    # postprocessor boundary using exact physical constants.
    power_scale = AVOGADRO * ELEMENTARY_CHARGE_C
    text = mp.upsert_parameter(
        text,
        f"Postprocessors/{w45.ENERGY_POWER_PP}",
        "scaling_factor",
        f"{power_scale:.17g}",
    )
    text = mp.upsert_parameter(
        text,
        f"Postprocessors/{energy.SEE_ENERGY_COUPLED_POWER_PP}",
        "scaling_factor",
        f"{power_scale:.17g}",
    )

    # Existing runtime observables are retained for downstream harness
    # compatibility, but now observe c_epsilon rather than a normalized state.
    for pp in (
        "s5r_n_epsilon_inventory",
        "s5r_n_epsilon_min",
        "s5r_n_epsilon_max",
    ):
        path = f"Postprocessors/{pp}"
        if mb.has_block(text, path):
            text = mp.upsert_parameter(text, path, "functor", C_EPSILON)

    # Add an explicit physical energy-density bridge and inventory in joules.
    mb.require_absent(text, f"FunctorMaterials/{ENERGY_DENSITY_J}")
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{ENERGY_DENSITY_J}]
    type = ADParsedFunctorMaterial
    property_name = {ENERGY_DENSITY_J}
    functor_names = '{C_EPSILON}'
    functor_symbols = 'ceps'
    expression = '{power_scale:.17g}*ceps'
    block = plasma
  []""",
    )
    for name, typ, functor, extra in (
        (ENERGY_INVENTORY_J, "ADElementIntegralFunctorPostprocessor", ENERGY_DENSITY_J, ""),
        (C_EPSILON_MIN, "ADElementExtremeFunctorValue", C_EPSILON, "\n    value_type = min"),
    ):
        mb.require_absent(text, f"Postprocessors/{name}")
        text = mb.insert_child_block(
            text,
            "Postprocessors",
            f"""  [{name}]
    type = {typ}
    functor = {functor}{extra}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
        )

    # The T1 energy-only compatibility bridge has no owner after T2.
    if mb.has_block(text, f"FunctorMaterials/{t1.ENERGY_COMPAT}"):
        text = mb.remove_block(text, f"FunctorMaterials/{t1.ENERGY_COMPAT}")

    return text, {
        **predecessor,
        "issue": 245,
        "claim": "t2_conservative_molar_electron_energy_no_energy_nref",
        "predecessor_issue": 243,
        "particle_solver_unknown": t1.LOG_E,
        "energy_solver_unknown": C_EPSILON,
        "electron_molar_density": f"{C_E_MOLAR}=exp({t1.LOG_E})",
        "mean_energy": f"mean_en_solved={C_EPSILON}/{C_E_MOLAR}",
        "physical_energy_density": f"{ENERGY_DENSITY_J}=N_A*e*{C_EPSILON}",
        "legacy_energy_compatibility_bridge_removed": True,
        "initial_mean_energy_eV": ENERGY_REFERENCE_EV,
    }


def audit_t2_input(text: str) -> dict[str, Any]:
    energy_residual_paths = [
        "FVKernels/s5r_n_epsilon_time",
        "FVKernels/s5r_n_epsilon_diffusion",
        "FVKernels/s5r_n_epsilon_drift",
        "FunctorMaterials/s5r_ei02_elastic_energy",
        "FVKernels/s5r_ei02_elastic_energy",
        "FunctorMaterials/s5r_ei17_elastic_energy",
        "FVKernels/s5r_ei17_elastic_energy",
        f"FVBCs/{w45.ENERGY_BC}",
        f"FunctorMaterials/{energy.SEE_ENERGY_MATERIAL}",
        f"FVBCs/{energy.SEE_ENERGY_BC}",
    ] + [f"FVKernels/s5r_energy_{channel.lower()}" for channel in s5.ENERGY_LOSS_EV]

    checks: dict[str, bool] = {
        # Accepted T1 particle side is unchanged.
        "particle_log_state_present": mb.has_block(text, f"Variables/{t1.LOG_E}"),
        "particle_old_state_absent": not mb.has_block(text, "Variables/n_e"),
        "particle_physical_bridge_exact": mp.get_parameter(
            text, "FunctorMaterials/electron_density_physical", "expression"
        ) == f"'{AVOGADRO:.17g}*exp(loge)'",
        "particle_source_no_nref": mp.get_parameter(
            text, "FVKernels/s5r_electron_source", "n_ref"
        ) is None,
        "particle_primary_sheath_log_molar": mp.get_parameter(
            text, f"FVBCs/{w45.PARTICLE_BC}", "log_molar_state"
        ) == "true",
        # T2 energy representation.
        "legacy_energy_state_absent": not mb.has_block(text, "Variables/n_epsilon"),
        "molar_energy_state_present": mb.has_block(text, f"Variables/{C_EPSILON}"),
        "direct_molar_density_present": mb.has_block(text, f"FunctorMaterials/{C_E_MOLAR}"),
        "direct_molar_density_exact": mp.get_parameter(
            text, f"FunctorMaterials/{C_E_MOLAR}", "expression"
        ) == "'exp(loge)'",
        "mean_energy_exact": mp.get_parameter(
            text, "FunctorMaterials/s5r_mean_energy", "expression"
        ) == "'ceps/ce'",
        "mean_energy_inputs_exact": mp.words(mp.get_parameter(
            text, "FunctorMaterials/s5r_mean_energy", "functor_names"
        ) or "") == [C_EPSILON, C_E_MOLAR],
        "energy_time_molar": mp.get_parameter(
            text, "FVKernels/s5r_n_epsilon_time", "variable"
        ) == C_EPSILON,
        "energy_diffusion_molar": mp.get_parameter(
            text, "FVKernels/s5r_n_epsilon_diffusion", "variable"
        ) == C_EPSILON,
        "energy_drift_molar": mp.get_parameter(
            text, "FVKernels/s5r_n_epsilon_drift", "variable"
        ) == C_EPSILON,
        "primary_energy_molar_mode": mp.get_parameter(
            text, f"FVBCs/{w45.ENERGY_BC}", "molar_energy_state"
        ) == "true",
        "primary_energy_uses_ce": mp.get_parameter(
            text, f"FVBCs/{w45.ENERGY_BC}", "electron_density"
        ) == C_E_MOLAR,
        "primary_energy_no_reference_parameter": mp.get_parameter(
            text, f"FVBCs/{w45.ENERGY_BC}", "energy_reference_eV"
        ) is None,
        "see_energy_uses_t1_molar_particle_flux": mp.words(mp.get_parameter(
            text, f"FunctorMaterials/{energy.SEE_ENERGY_MATERIAL}", "functor_names"
        ) or "") == [t1.PHYSICAL_SEE_FUNCTOR],
        "see_energy_four_ev_exact": mp.get_parameter(
            text, f"FunctorMaterials/{energy.SEE_ENERGY_MATERIAL}", "expression"
        ) == "'4*see_molar'",
        "see_energy_targets_molar_state": mp.get_parameter(
            text, f"FVBCs/{energy.SEE_ENERGY_BC}", "variable"
        ) == C_EPSILON,
        "legacy_energy_compat_absent": not mb.has_block(text, f"FunctorMaterials/{t1.ENERGY_COMPAT}"),
        "physical_energy_density_exact": mp.get_parameter(
            text, f"FunctorMaterials/{ENERGY_DENSITY_J}", "expression"
        ) == f"'{AVOGADRO * ELEMENTARY_CHARGE_C:.17g}*ceps'",
        "automatic_scaling_on": mp.get_parameter(text, "Executioner", "automatic_scaling") == "true",
    }

    for channel, loss_eV in s5.ENERGY_LOSS_EV.items():
        path = f"FVKernels/s5r_energy_{channel.lower()}"
        checks[f"energy_loss:{channel}"] = (
            mp.get_parameter(text, path, "variable") == C_EPSILON
            and math.isclose(float(mp.get_parameter(text, path, "coef") or "nan"), -loss_eV,
                             rel_tol=0.0, abs_tol=1.0e-14)
            and mp.get_parameter(text, path, "v") == s5.PROGRESS[channel]
        )

    checks["energy_residual_has_no_nref_token"] = all(
        "n_ref" not in _block_text(text, path) for path in energy_residual_paths
    )
    checks["energy_residual_has_no_reference_scale_parameter"] = all(
        "energy_reference_eV" not in _block_text(text, path) for path in energy_residual_paths
    )

    failed = sorted(name for name, ok in checks.items() if not ok)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def self_test() -> int:
    text, _ = build_t2_input()
    audit = audit_t2_input(text)
    if audit["status"] != "PASS":
        raise RuntimeError(audit)

    # Mutation: normalized wall-energy mode must be detected.
    mutated = mp.upsert_parameter(text, f"FVBCs/{w45.ENERGY_BC}", "molar_energy_state", "false")
    if audit_t2_input(mutated)["status"] != "FAIL":
        raise RuntimeError("T2 mutation self-test failed to reject normalized primary-energy mode")

    # Mutation: wrong SEE energy must be detected.
    mutated = mp.upsert_parameter(
        text, f"FunctorMaterials/{energy.SEE_ENERGY_MATERIAL}", "expression", "'3*see_molar'"
    )
    if audit_t2_input(mutated)["status"] != "FAIL":
        raise RuntimeError("T2 mutation self-test failed to reject non-4-eV SEE mapping")

    print("Issue245 T2 static audit PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
