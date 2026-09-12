#!/usr/bin/env python3
"""Issue #217 sheath-consistent primary electron particle/energy wall closure.

This governed runner replaces only the historical unsuppressed primary-electron
particle and energy wall owners on the accepted Stage-6 composition. Ion wall
transport, ion-induced SEE, the 4 eV SEE energy source, Stage-5 chemistry, and
solved electron-energy transport retain their accepted ownership.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue27_surface_reactions import final_stage6
from experiments.Issue27_surface_reactions.controlled_wall import combined, see as a8
from experiments.Issue27_surface_reactions.controlled_wall import electron_wall as a7
from experiments.historical_recipe_support import issue26_energy_chain as energy
from experiments.historical_recipe_support.issue26_e1 import ENERGY_REFERENCE_EV
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import stage_case, validate_case_references

ROOT = Path(__file__).resolve().parents[2]
SOURCE = s5r.SOURCE
WALLS = tuple(combined.PLASMA_WALLS)
ALL_BOUNDARIES = ("inlet", "outlet", *WALLS)
ELEMENTARY_CHARGE_C = 1.602176634e-19
AVOGADRO = 6.02214076e23
ELECTRON_MASS_KG = 9.1093837139e-31
PI = math.pi
DT_S = 1.0e-10
END_TIME_S = 1.0e-10
RUNTIME_REL_TOL = 1.0e-3
ALGEBRAIC_REL_TOL = 1.0e-10
COMPOSITION_ABS_TOL = 1.0e-8
ELECTRON_DENSITY_FLOOR = -1.0e-12

PARTICLE_BC = "issue217_grounded_sheath_primary_particle"
PARTICLE_PP = "issue217_grounded_sheath_primary_particle_rate"
ENERGY_BC = "issue217_grounded_sheath_primary_energy"
ENERGY_RATE_PP = "issue217_grounded_sheath_primary_energy_rate"
ENERGY_POWER_PP = "issue217_grounded_sheath_primary_energy_power_W"
RHO_MIN_PP = "issue217_rho_q_min"
RHO_MAX_PP = "issue217_rho_q_max"
PHI_MIN_PP = "issue217_phi_min"
PHI_MAX_PP = "issue217_phi_max"

PARTICLE_CPP = ROOT / "physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathCollectionBC.C"
ENERGY_CPP = ROOT / "physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.C"
SHARED_HELPER = ROOT / "physics_app/include/fvbcs/PhysicsGroundedElectronSheathFlux.h"


class Issue217Error(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _words(text: str, path: str, parameter: str) -> tuple[str, ...]:
    return tuple(mp.words(mp.get_parameter(text, path, parameter) or ""))


def _add_pp(text: str, name: str, body: str) -> str:
    path = f"Postprocessors/{name}"
    if mb.has_block(text, path):
        return text
    return mb.insert_child_block(text, "Postprocessors", f"  [{name}]\n{body}\n  []")


def _remove_historical_primary_owners(text: str) -> str:
    for path in (
        f"FunctorMaterials/{a7.THERMAL_MATERIAL}",
        f"FVBCs/{a7.THERMAL_BC}",
        f"Postprocessors/{a7.THERMAL_PP}",
        f"FunctorMaterials/{energy.ENERGY_WALL_THERMAL_MATERIAL}",
        f"FVBCs/{energy.ENERGY_WALL_THERMAL_BC}",
        f"Postprocessors/{energy.ENERGY_WALL_THERMAL_RATE_PP}",
        f"Postprocessors/{energy.ENERGY_WALL_THERMAL_POWER_PP}",
    ):
        if not mb.has_block(text, path):
            raise Issue217Error(f"missing historical primary wall owner: {path}")
        text = mb.remove_block(text, path)
    return text


def _insert_sheath_primary_owners(text: str, *, n_ref: float) -> str:
    wall_list = "'" + " ".join(WALLS) + "'"
    for path in (
        f"FVBCs/{PARTICLE_BC}",
        f"Postprocessors/{PARTICLE_PP}",
        f"FVBCs/{ENERGY_BC}",
        f"Postprocessors/{ENERGY_RATE_PP}",
        f"Postprocessors/{ENERGY_POWER_PP}",
    ):
        mb.require_absent(text, path)

    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{PARTICLE_BC}]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = n_e
    boundary = {wall_list}
    mean_electron_energy = mean_en_solved
    potential = potential_plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{PARTICLE_PP}]
    type = SideFVFluxBCIntegral
    boundary = {wall_list}
    fvbcs = '{PARTICLE_BC}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{ENERGY_BC}]
    type = PhysicsFVElectronGroundedSheathEnergyBC
    variable = n_epsilon
    boundary = {wall_list}
    electron_density = n_e
    mean_electron_energy = mean_en_solved
    potential = potential_plasma
    energy_reference_eV = {ENERGY_REFERENCE_EV:.17g}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{ENERGY_RATE_PP}]
    type = SideFVFluxBCIntegral
    boundary = {wall_list}
    fvbcs = '{ENERGY_BC}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    energy_scale_W_per_norm_rate = n_ref * ENERGY_REFERENCE_EV * ELEMENTARY_CHARGE_C
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{ENERGY_POWER_PP}]
    type = ScalePostprocessor
    value = {ENERGY_RATE_PP}
    scaling_factor = {energy_scale_W_per_norm_rate:.17g}
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    return text


def _instrument(text: str) -> str:
    text = mp.upsert_parameter(text, "Executioner", "dt", f"{DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{END_TIME_S:.17g}")
    for pp in (
        "n_e_inventory",
        "n_e_min",
        "n_e_max",
        "n_e_avg",
        "r31_charge_integral",
        "r31_gauss_flux_charge",
        "sum_w_min",
        "sum_w_max",
        "s5r_n_epsilon_inventory",
        "s5r_n_epsilon_min",
        "s5r_n_epsilon_max",
        "s5r_mean_en_avg",
        "s5r_mean_en_min",
        "s5r_mean_en_max",
        PARTICLE_PP,
        ENERGY_RATE_PP,
        ENERGY_POWER_PP,
        a8.SEE_PP,
        energy.SEE_ENERGY_RATE_PP,
        energy.SEE_ENERGY_COUPLED_POWER_PP,
    ):
        path = f"Postprocessors/{pp}"
        if mb.has_block(text, path):
            text = mp.upsert_parameter(text, path, "execute_on", "'INITIAL TIMESTEP_END'")

    text = _add_pp(
        text,
        RHO_MIN_PP,
        "    type = ADElementExtremeFunctorValue\n"
        "    functor = charge_density\n"
        "    value_type = min\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    text = _add_pp(
        text,
        RHO_MAX_PP,
        "    type = ADElementExtremeFunctorValue\n"
        "    functor = charge_density\n"
        "    value_type = max\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    text = _add_pp(
        text,
        PHI_MIN_PP,
        "    type = ElementExtremeValue\n"
        "    variable = potential_plasma\n"
        "    value_type = min\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    text = _add_pp(
        text,
        PHI_MAX_PP,
        "    type = ElementExtremeValue\n"
        "    variable = potential_plasma\n"
        "    value_type = max\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    return text


def _construction_audit(text: str, *, predecessor_audit: Mapping[str, Any]) -> dict[str, Any]:
    drift_path = "FVKernels/n_e_drift"
    avoid = _words(text, drift_path, "boundaries_to_avoid")
    forced = _words(text, drift_path, "boundaries_to_force")
    wall_set = set(WALLS)

    checks: dict[str, bool] = {
        "predecessor_stage6_accepted_composition": predecessor_audit.get("status") == "PASS",
        "historical_primary_particle_material_absent": not mb.has_block(text, f"FunctorMaterials/{a7.THERMAL_MATERIAL}"),
        "historical_primary_particle_bc_absent": not mb.has_block(text, f"FVBCs/{a7.THERMAL_BC}"),
        "historical_primary_particle_pp_absent": not mb.has_block(text, f"Postprocessors/{a7.THERMAL_PP}"),
        "historical_primary_energy_material_absent": not mb.has_block(text, f"FunctorMaterials/{energy.ENERGY_WALL_THERMAL_MATERIAL}"),
        "historical_primary_energy_bc_absent": not mb.has_block(text, f"FVBCs/{energy.ENERGY_WALL_THERMAL_BC}"),
        "historical_primary_energy_rate_pp_absent": not mb.has_block(text, f"Postprocessors/{energy.ENERGY_WALL_THERMAL_RATE_PP}"),
        "historical_primary_energy_power_pp_absent": not mb.has_block(text, f"Postprocessors/{energy.ENERGY_WALL_THERMAL_POWER_PP}"),
        "new_particle_owner_present": mb.has_block(text, f"FVBCs/{PARTICLE_BC}"),
        "new_energy_owner_present": mb.has_block(text, f"FVBCs/{ENERGY_BC}"),
        "particle_owner_type": mp.get_parameter(text, f"FVBCs/{PARTICLE_BC}", "type") == "PhysicsFVElectronGroundedSheathCollectionBC",
        "energy_owner_type": mp.get_parameter(text, f"FVBCs/{ENERGY_BC}", "type") == "PhysicsFVElectronGroundedSheathEnergyBC",
        "particle_wall_set_exact": set(_words(text, f"FVBCs/{PARTICLE_BC}", "boundary")) == wall_set,
        "energy_wall_set_exact": set(_words(text, f"FVBCs/{ENERGY_BC}", "boundary")) == wall_set,
        "particle_uses_solved_mean_energy": mp.get_parameter(text, f"FVBCs/{PARTICLE_BC}", "mean_electron_energy") == "mean_en_solved",
        "particle_uses_plasma_potential": mp.get_parameter(text, f"FVBCs/{PARTICLE_BC}", "potential") == "potential_plasma",
        "energy_uses_ne": mp.get_parameter(text, f"FVBCs/{ENERGY_BC}", "electron_density") == "n_e",
        "energy_uses_solved_mean_energy": mp.get_parameter(text, f"FVBCs/{ENERGY_BC}", "mean_electron_energy") == "mean_en_solved",
        "energy_uses_plasma_potential": mp.get_parameter(text, f"FVBCs/{ENERGY_BC}", "potential") == "potential_plasma",
        "energy_reference_frozen": math.isclose(float(mp.get_parameter(text, f"FVBCs/{ENERGY_BC}", "energy_reference_eV") or "nan"), ENERGY_REFERENCE_EV, rel_tol=0.0, abs_tol=1.0e-12),
        "see_particle_owner_preserved": mb.has_block(text, f"FVBCs/{a8.SEE_BC}") and float(mp.get_parameter(text, f"FVBCs/{a8.SEE_BC}", "factor") or "nan") == 1.0,
        "see_energy_owner_preserved": mb.has_block(text, f"FVBCs/{energy.SEE_ENERGY_BC}") and float(mp.get_parameter(text, f"FVBCs/{energy.SEE_ENERGY_BC}", "factor") or "nan") == 1.0,
        "see_particle_wall_set_exact": set(_words(text, f"FVBCs/{a8.SEE_BC}", "boundary")) == wall_set,
        "see_energy_wall_set_exact": set(_words(text, f"FVBCs/{energy.SEE_ENERGY_BC}", "boundary")) == wall_set,
        "bulk_electron_drift_avoids_all_boundaries": avoid == ALL_BOUNDARIES,
        "bulk_electron_drift_forced_empty": forced == (),
        "a6_matched_electron_ledger_absent": not mb.has_block(text, f"FVBCs/{combined.ELECTRON_BC}"),
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "boundaries_to_avoid": list(avoid),
        "boundaries_to_force": list(forced),
    }


def _cpp_contract_audit() -> dict[str, Any]:
    particle = PARTICLE_CPP.read_text(encoding="utf-8")
    energy_src = ENERGY_CPP.read_text(encoding="utf-8")
    helper = SHARED_HELPER.read_text(encoding="utf-8")
    checks = {
        "shared_helper_exists": SHARED_HELPER.is_file(),
        "particle_consumes_shared_relation": 'PhysicsGroundedElectronSheath::primaryParticleFluxHat' in particle,
        "energy_consumes_shared_relation": 'PhysicsGroundedElectronSheath::primaryEnergyFluxHat' in energy_src,
        "particle_plasma_cell_state": "elemArg()" in particle and "neighborArg()" in particle,
        "energy_plasma_cell_state": "elemArg()" in energy_src and "neighborArg()" in energy_src,
        "particle_face_state_not_used": "singleSidedFaceArg" not in particle,
        "energy_face_state_not_used": "singleSidedFaceArg" not in energy_src,
        "shared_particle_suppression": "exp(-effective_drop_V / electron_temperature_eV)" in helper,
        "shared_energy_per_collected_electron": "2.0 * electron_temperature_eV + effective_drop_V" in helper,
        "energy_owner_has_no_see_term": "see_number_flux" not in energy_src,
        "same_negative_drop_tolerance": "negative_drop_tolerance_V" in particle and "negative_drop_tolerance_V" in energy_src,
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def _analytic_contract_audit() -> dict[str, Any]:
    mean_energy_eV = ENERGY_REFERENCE_EV
    te_eV = (2.0 / 3.0) * mean_energy_eV
    cbar = math.sqrt(8.0 * ELEMENTARY_CHARGE_C * te_eV / (PI * ELECTRON_MASS_KG))

    def values(drop_v: float) -> tuple[float, float]:
        particle = 0.25 * cbar * math.exp(-drop_v / te_eV)
        energy_hat = particle * (2.0 * te_eV + drop_v) / ENERGY_REFERENCE_EV
        return particle, energy_hat

    p0, e0 = values(0.0)
    p10, e10 = values(10.0)
    p100, e100 = values(100.0)
    checks = {
        "zero_drop_particle_quarter_maxwellian": math.isclose(p0, 0.25 * cbar, rel_tol=1.0e-15),
        "zero_drop_energy_per_collected_electron_2Te": math.isclose(e0 / p0 * ENERGY_REFERENCE_EV, 2.0 * te_eV, rel_tol=1.0e-15),
        "positive_drop_suppresses_particle": 0.0 < p10 < p0,
        "positive_drop_suppresses_total_primary_energy_flux": 0.0 < e10 < e0,
        "large_drop_particle_vanishes": p100 / p0 < 1.0e-10,
        "large_drop_energy_vanishes": e100 / e0 < 1.0e-8,
        "wrong_sign_would_amplify": math.exp(+10.0 / te_eV) > 1.0,
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "mean_energy_eV": mean_energy_eV,
        "electron_temperature_eV": te_eV,
        "mean_speed_m_s": cbar,
        "zero_drop": {"particle_flux_hat_m_s": p0, "energy_flux_hat_m_s": e0},
        "ten_volt_drop": {"particle_flux_hat_m_s": p10, "energy_flux_hat_m_s": e10},
        "hundred_volt_drop": {"particle_flux_hat_m_s": p100, "energy_flux_hat_m_s": e100},
    }


def _base_stage6() -> tuple[str, dict[str, Any]]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    text, meta = final_stage6.build_stage6_final_input(base)
    predecessor_audit = final_stage6.audit_stage6_final_input(text)
    if predecessor_audit["status"] != "PASS":
        raise Issue217Error(f"predecessor Stage-6 audit failed: {predecessor_audit['failed_checks']}")
    return text, {**meta, "predecessor_audit": predecessor_audit}


def build_issue217_input() -> tuple[str, dict[str, Any]]:
    text, predecessor = _base_stage6()
    n_ref = float(predecessor["electron_reference_density_m3"])
    text = _remove_historical_primary_owners(text)
    text = _insert_sheath_primary_owners(text, n_ref=n_ref)
    text = _instrument(text)
    audit = _construction_audit(text, predecessor_audit=predecessor["predecessor_audit"])
    if audit["status"] != "PASS":
        raise Issue217Error(f"Issue-217 construction audit failed: {audit['failed_checks']}")
    return text, {
        "issue": 217,
        "parent_controller": 211,
        "predecessor_issue": 215,
        "electron_reference_density_m3": n_ref,
        "energy_reference_eV": ENERGY_REFERENCE_EV,
        "timestep_s": DT_S,
        "end_time_s": END_TIME_S,
        "wall_boundaries": list(WALLS),
        "claim": "grounded_sheath_primary_particle_energy_same_population_precursor",
        "predecessor": predecessor,
        "audit": audit,
    }


def _negative_controls() -> dict[str, Any]:
    historical_text, predecessor = _base_stage6()
    n_ref = float(predecessor["electron_reference_density_m3"])

    # Deliberately replace only the particle owner and keep the old unsuppressed
    # primary-energy owner. The Issue-217 ownership audit must reject it.
    bad = historical_text
    for path in (
        f"FunctorMaterials/{a7.THERMAL_MATERIAL}",
        f"FVBCs/{a7.THERMAL_BC}",
        f"Postprocessors/{a7.THERMAL_PP}",
    ):
        bad = mb.remove_block(bad, path)
    wall_list = "'" + " ".join(WALLS) + "'"
    bad = mb.insert_child_block(
        bad,
        "FVBCs",
        f"""  [{PARTICLE_BC}]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = n_e
    boundary = {wall_list}
    mean_electron_energy = mean_en_solved
    potential = potential_plasma
  []""",
    )
    bad = mb.insert_child_block(
        bad,
        "Postprocessors",
        f"""  [{PARTICLE_PP}]
    type = SideFVFluxBCIntegral
    boundary = {wall_list}
    fvbcs = '{PARTICLE_BC}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    bad_audit = _construction_audit(bad, predecessor_audit=predecessor["predecessor_audit"])

    good, _ = build_issue217_input()
    forced = mp.upsert_parameter(good, "FVKernels/n_e_drift", "boundaries_to_avoid", "'inlet outlet'")
    forced = mp.upsert_parameter(forced, "FVKernels/n_e_drift", "boundaries_to_force", wall_list)
    forced_audit = _construction_audit(forced, predecessor_audit=predecessor["predecessor_audit"])

    checks = {
        "unsuppressed_energy_with_sheath_particle_rejected": bad_audit["status"] == "FAIL",
        "forced_bulk_electron_wall_drift_rejected": forced_audit["status"] == "FAIL",
        "positive_integrated_construction_passes": _construction_audit(good, predecessor_audit=predecessor["predecessor_audit"])["status"] == "PASS",
        "n_ref_positive": n_ref > 0.0,
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "unsuppressed_energy_audit": bad_audit,
        "forced_drift_audit": forced_audit,
    }


def self_test() -> dict[str, Any]:
    cpp = _cpp_contract_audit()
    analytic = _analytic_contract_audit()
    negative = _negative_controls()
    text, meta = build_issue217_input()
    checks = {
        "cpp_contract": cpp["status"] == "PASS",
        "analytic_contract": analytic["status"] == "PASS",
        "negative_controls": negative["status"] == "PASS",
        "construction": meta["audit"]["status"] == "PASS",
        "semantic_replacement_present": a7.THERMAL_BC not in text and energy.ENERGY_WALL_THERMAL_BC not in text,
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "cpp": cpp,
        "analytic": analytic,
        "negative_controls": negative,
    }


def _stage(case_dir: Path) -> tuple[str, dict[str, Any], dict[str, Any]]:
    text, meta = build_issue217_input()
    staged = stage_case(
        SOURCE,
        case_dir,
        input_text=text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    s5r._copy_runtime_assets(case_dir)
    references = validate_case_references(case_dir)
    (case_dir / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return text, meta, {"staging": staged, "references": references}


def _physical(value: float) -> float:
    return abs(float(value))


def _rel_defect(measured: float, expected: float, *components: float) -> float:
    scale = max(abs(expected), *(abs(value) for value in components), 1.0e-300)
    return abs(measured - expected) / scale


def _wall_observables(row: Mapping[str, str]) -> dict[str, Any]:
    charged: dict[str, Any] = {}
    finite = True
    for species in combined.CHARGED:
        surface = 0.0
        migration = 0.0
        by_wall: dict[str, Any] = {}
        for wall in combined.PLASMA_WALLS:
            _, _, surface_pp, migration_pp = combined._charged_names(species, wall)
            s = _physical(s5r._num(row, surface_pp))
            m = _physical(s5r._num(row, migration_pp))
            finite = finite and math.isfinite(s) and math.isfinite(m)
            by_wall[wall] = {"surface_mass_rate_kg_s": s, "migration_mass_rate_kg_s": m}
            surface += s
            migration += m
        charged[species] = {
            "surface_mass_rate_kg_s": surface,
            "migration_mass_rate_kg_s": migration,
            "total_mass_rate_kg_s": surface + migration,
            "by_wall": by_wall,
        }
    return {"charged": charged, "finite": finite}


def _runtime_metrics(case_dir: Path, *, input_text: str, meta: Mapping[str, Any]) -> dict[str, Any]:
    csv_path = case_dir / "input_out.csv"
    rows = s5r._read_rows(csv_path)
    if len(rows) < 2:
        raise Issue217Error("need INITIAL and TIMESTEP_END rows")
    initial = rows[0]
    final = rows[-1]
    t0 = s5r._num(initial, "time")
    t1 = s5r._num(final, "time")
    dt = t1 - t0
    if dt <= 0.0:
        raise Issue217Error(f"non-positive runtime dt={dt}")

    volume = s5r._num(final, "domain_volume")
    n_ref = float(meta["electron_reference_density_m3"])
    wall = _wall_observables(final)

    primary_rate_norm = _physical(s5r._num(final, PARTICLE_PP))
    see_rate_norm = _physical(s5r._num(final, a8.SEE_PP))
    primary_rate = primary_rate_norm * n_ref
    see_rate = see_rate_norm * n_ref

    electron_accumulation = (
        s5r._num(final, "n_e_inventory") - s5r._num(initial, "n_e_inventory")
    ) / dt
    volumetric_electron_rate = s5r._num(final, "s5r_electron_source_avg") * volume
    expected_electron_rate = volumetric_electron_rate + see_rate - primary_rate
    electron_defect = _rel_defect(
        electron_accumulation,
        expected_electron_rate,
        volumetric_electron_rate,
        see_rate,
        primary_rate,
    )

    coefficients = s5r._energy_coefficients(input_text)
    volumetric_energy_norm_rate = s5r._energy_source_density(final, coefficients) * volume
    energy_accum_norm_rate = (
        s5r._num(final, "s5r_n_epsilon_inventory")
        - s5r._num(initial, "s5r_n_epsilon_inventory")
    ) / dt
    energy_scale = n_ref * ENERGY_REFERENCE_EV * ELEMENTARY_CHARGE_C
    primary_power = _physical(s5r._num(final, ENERGY_POWER_PP))
    see_power = _physical(s5r._num(final, energy.SEE_ENERGY_COUPLED_POWER_PP))
    expected_energy_norm_rate = (
        volumetric_energy_norm_rate - primary_power / energy_scale + see_power / energy_scale
    )
    energy_defect = _rel_defect(
        energy_accum_norm_rate,
        expected_energy_norm_rate,
        volumetric_energy_norm_rate,
        primary_power / energy_scale,
        see_power / energy_scale,
    )

    expected_see_power = see_rate * ELEMENTARY_CHARGE_C * 4.0
    see_mapping_defect = _rel_defect(see_power, expected_see_power)

    ion_rates: dict[str, float] = {}
    for species, cfg in combined.CHARGED.items():
        ion_rates[species] = (
            AVOGADRO
            * float(wall["charged"][species]["total_mass_rate_kg_s"])
            / float(cfg["molar_mass"])
        )
    positive_ion_charge_delta = -ELEMENTARY_CHARGE_C * (ion_rates["O2p"] + ion_rates["Op"]) * dt
    negative_ion_charge_delta = +ELEMENTARY_CHARGE_C * ion_rates["Om"] * dt
    primary_electron_charge_delta = +ELEMENTARY_CHARGE_C * primary_rate * dt
    see_electron_charge_delta = -ELEMENTARY_CHARGE_C * see_rate * dt
    expected_charge_delta = (
        positive_ion_charge_delta
        + negative_ion_charge_delta
        + primary_electron_charge_delta
        + see_electron_charge_delta
    )
    measured_charge_delta = (
        s5r._num(final, "r31_charge_integral") - s5r._num(initial, "r31_charge_integral")
    )
    charge_scale = max(
        abs(positive_ion_charge_delta)
        + abs(negative_ion_charge_delta)
        + abs(primary_electron_charge_delta)
        + abs(see_electron_charge_delta),
        1.0e-300,
    )
    charge_defect = abs(measured_charge_delta - expected_charge_delta) / charge_scale

    gauss = s5r._gauss_evidence(csv_path)
    physical_rows = [row for row in rows if s5r._num(row, "time") > 1.0e-15]
    state = s5r._state_evidence(physical_rows)
    composition_error = max(
        abs(s5r._num(final, "sum_w_min") - 1.0),
        abs(s5r._num(final, "sum_w_max") - 1.0),
    )

    return {
        "dt_s": dt,
        "state": state,
        "gauss": gauss,
        "wall": wall,
        "electron_particle": {
            "accumulation_rate_s-1": electron_accumulation,
            "volumetric_source_rate_s-1": volumetric_electron_rate,
            "primary_wall_loss_rate_s-1": primary_rate,
            "see_wall_source_rate_s-1": see_rate,
            "expected_rate_s-1": expected_electron_rate,
            "relative_defect": electron_defect,
        },
        "electron_energy": {
            "accumulation_normalized_rate": energy_accum_norm_rate,
            "volumetric_source_normalized_rate": volumetric_energy_norm_rate,
            "primary_wall_power_W": primary_power,
            "see_wall_power_W": see_power,
            "expected_normalized_rate": expected_energy_norm_rate,
            "relative_defect": energy_defect,
        },
        "see_4eV_mapping": {
            "expected_power_W": expected_see_power,
            "measured_power_W": see_power,
            "relative_defect": see_mapping_defect,
        },
        "charge": {
            "ion_incident_particle_rate_s-1": ion_rates,
            "positive_ion_charge_delta_C": positive_ion_charge_delta,
            "negative_ion_charge_delta_C": negative_ion_charge_delta,
            "primary_electron_charge_delta_C": primary_electron_charge_delta,
            "see_electron_charge_delta_C": see_electron_charge_delta,
            "expected_delta_C": expected_charge_delta,
            "measured_delta_C": measured_charge_delta,
            "relative_defect_over_boundary_current_scale": charge_defect,
        },
        "composition_max_abs_error": composition_error,
        "n_e_min": s5r._num(final, "n_e_min"),
        "n_epsilon_min": s5r._num(final, "s5r_n_epsilon_min"),
        "mean_energy_avg_eV": s5r._num(final, "s5r_mean_en_avg"),
        "phi_min_V": s5r._num(final, PHI_MIN_PP),
        "phi_max_V": s5r._num(final, PHI_MAX_PP),
        "rho_q_min_C_m3": s5r._num(final, RHO_MIN_PP),
        "rho_q_max_C_m3": s5r._num(final, RHO_MAX_PP),
    }


def _evaluate(meta: Mapping[str, Any], metrics: Mapping[str, Any], *, runtime_ok: bool) -> dict[str, Any]:
    state = metrics["state"]
    gauss = metrics["gauss"]
    gates = {
        "G01_construction_ownership": meta["audit"]["status"] == "PASS",
        "G02_stage5_state_invariants": state.get("hard_pass") is True,
        "G03_wall_runtime_observables": metrics["wall"]["finite"] is True,
        "G04_electron_particle_balance": metrics["electron_particle"]["relative_defect"] <= s5r.GENERIC_COUPLED_BALANCE_REL_TOL,
        "G05_electron_energy_balance": metrics["electron_energy"]["relative_defect"] <= s5r.GENERIC_COUPLED_BALANCE_REL_TOL,
        "G06_four_ev_see_mapping": metrics["see_4eV_mapping"]["relative_defect"] <= ALGEBRAIC_REL_TOL,
        "G07_boundary_current_charge_closure": metrics["charge"]["relative_defect_over_boundary_current_scale"] <= RUNTIME_REL_TOL,
        "G08_gauss_closure": gauss.get("status") == "MEASURED" and gauss.get("relative_defect", math.inf) <= s5r.MAX_GAUSS_RELATIVE_DEFECT,
        "G09_convergence_positivity": (
            runtime_ok
            and metrics["n_e_min"] >= ELECTRON_DENSITY_FLOOR
            and metrics["n_epsilon_min"] > 0.0
            and metrics["mean_energy_avg_eV"] > 0.0
            and metrics["composition_max_abs_error"] <= COMPOSITION_ABS_TOL
        ),
        "G10_primary_energy_owner_active": metrics["electron_energy"]["primary_wall_power_W"] > 0.0,
    }
    return {"gates": gates, "scientific_hard_pass": all(gates.values())}


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue217Error(f"invalid physics-opt: {exe}")

    p0 = self_test()
    if p0["status"] != "PASS":
        raise Issue217Error(f"P0 self-test failed: {p0}")

    out = args.results_root.resolve()
    case_dir = out / "case"
    logs = out / "logs"
    out.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    input_text, meta, staging = _stage(case_dir)
    p2 = s5r._p2(exe, case_dir, logs / "issue217_p2.log", timeout=args.timeout)
    runtime: dict[str, Any] = {"returncode": None}
    metrics: dict[str, Any] = {"status": "NOT_RUN"}
    decision = {"gates": {}, "scientific_hard_pass": False}

    if p2["returncode"] == 0:
        runtime = s5r._runtime(exe, case_dir, logs / "issue217_runtime.log", timeout=args.timeout)
        if runtime.get("returncode") == 0:
            metrics = _runtime_metrics(case_dir, input_text=input_text, meta=meta)
            decision = _evaluate(meta, metrics, runtime_ok=True)

    summary = {
        "schema_version": 1,
        "issue": 217,
        "parent_controller": 211,
        "blocks_issue": 216,
        "repository_head": os.environ.get("GITHUB_SHA"),
        "runtime_authority": "governed_ci_provenance_controlled",
        "physics_opt_realpath": str(exe),
        "physics_opt_sha256": _sha256(exe),
        "p0": p0,
        "construction": meta,
        "staging": staging,
        "p2": p2,
        "runtime": runtime,
        "metrics": metrics,
        "decision": decision,
        "claim_boundary": {
            "on_green": "classical grounded electron-repelling sheath primary particle/energy same-population precursor accepted",
            "does_not_establish": [
                "W5 longer multi-step acceptance (#216)",
                "floating conductor closure",
                "dielectric sigma_s",
                "electron-attracting/inverse/SCL sheath branches",
                "electron-induced material-dependent SEE",
                "RF/Maxwell powered ICP closure (#202-#208)",
            ],
        },
        "status": "ISSUE217_SHEATH_ENERGY_ACCEPTED" if decision.get("scientific_hard_pass") is True else "ISSUE217_SHEATH_ENERGY_FAIL",
    }
    summary_path = out / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(summary_path.read_text(encoding="utf-8"))
    return 0 if decision.get("scientific_hard_pass") is True else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue217-sheath-energy-results"))
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.physics_opt is None:
        parser.error("--physics-opt is required unless --self-test is used")
    if args.timeout <= 0.0:
        parser.error("--timeout must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
