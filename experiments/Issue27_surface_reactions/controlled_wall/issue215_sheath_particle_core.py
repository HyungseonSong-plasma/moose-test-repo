import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from experiments.Issue27_surface_reactions.controlled_wall import combined as a6
from experiments.Issue27_surface_reactions.controlled_wall import electron_wall as a7
from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue193_a8_see_acceptance.run import _promote_current_acceptance_types
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import stage_case

ROOT = Path("/workspace")
OUT = ROOT / "issue215-sheath-particle-results"
CASES = OUT / "cases"
LOGS = OUT / "logs"
SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0"
EXE = ROOT / "physics_app/physics-opt"
CPP_SOURCE = ROOT / "physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathCollectionBC.C"

ELEMENTARY_CHARGE_C = 1.602176634e-19
AVOGADRO = 6.02214076e23
ELECTRON_MASS_KG = 9.1093837139e-31
BASELINE_DT = 1.0e-10
REFINED_DT = 5.0e-11
TARGET_END = 2.0e-10
DTS = (BASELINE_DT, REFINED_DT)
WALLS = tuple(a6.PLASMA_WALLS)
ALL_BOUNDARIES = ("inlet", "outlet", *WALLS)
SHEATH_BC = "issue215_electron_grounded_sheath_collection"
SHEATH_PP = "issue215_electron_grounded_sheath_rate"
SPEC = json.loads(
    (ROOT / "experiments/Issue27_surface_reactions/A7_comsol_electron_wall/experiment.json").read_text()
)
PARAMS = SPEC["parameters"]
BASE_TEXT = (SOURCE / "heavy_base.i").read_text()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def words(text: str, path: str, parameter: str) -> tuple[str, ...]:
    return tuple(mp.words(mp.get_parameter(text, path, parameter) or ""))


def add_pp(text: str, name: str, body: str) -> str:
    path = f"Postprocessors/{name}"
    if mb.has_block(text, path):
        return text
    return mb.insert_child_block(text, "Postprocessors", f"  [{name}]\n{body}\n  []")


def replace_primary_wall_owner(text: str) -> str:
    for path in (
        f"FunctorMaterials/{a7.THERMAL_MATERIAL}",
        f"FVBCs/{a7.THERMAL_BC}",
        f"Postprocessors/{a7.THERMAL_PP}",
    ):
        if not mb.has_block(text, path):
            raise RuntimeError(f"missing historical primary electron owner: {path}")
        text = mb.remove_block(text, path)

    wall_list = "'" + " ".join(WALLS) + "'"
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{SHEATH_BC}]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = n_e
    boundary = {wall_list}
    mean_electron_energy = mean_en
    potential = potential_plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{SHEATH_PP}]
    type = SideFVFluxBCIntegral
    boundary = {wall_list}
    fvbcs = '{SHEATH_BC}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    return text


def instrument(text: str, *, dt: float, primary_pp: str) -> str:
    text = mp.upsert_parameter(text, "Executioner", "dt", f"{dt:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{TARGET_END:.17g}")
    for pp in (
        "n_e_inventory",
        "n_e_min",
        "n_e_max",
        "n_e_avg",
        "r31_charge_integral",
        "r31_gauss_flux_charge",
        "sum_w_min",
        "sum_w_max",
        primary_pp,
    ):
        if mb.has_block(text, f"Postprocessors/{pp}"):
            text = mp.upsert_parameter(
                text, f"Postprocessors/{pp}", "execute_on", "'INITIAL TIMESTEP_END'"
            )
    text = add_pp(
        text,
        "issue215_rho_q_min",
        "    type = ADElementExtremeFunctorValue\n"
        "    functor = charge_density\n"
        "    value_type = min\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    text = add_pp(
        text,
        "issue215_rho_q_max",
        "    type = ADElementExtremeFunctorValue\n"
        "    functor = charge_density\n"
        "    value_type = max\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    text = add_pp(
        text,
        "issue215_phi_min",
        "    type = ElementExtremeValue\n"
        "    variable = potential_plasma\n"
        "    value_type = min\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    text = add_pp(
        text,
        "issue215_phi_max",
        "    type = ElementExtremeValue\n"
        "    variable = potential_plasma\n"
        "    value_type = max\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    return text


def construction_audit(text: str, *, sheath: bool) -> dict:
    drift_path = "FVKernels/n_e_drift"
    avoid = words(text, drift_path, "boundaries_to_avoid")
    forced = words(text, drift_path, "boundaries_to_force")
    checks = {
        "current_drift_type": mp.get_parameter(text, drift_path, "type")
        == "PhysicsFVElectrostaticDrift",
        "bulk_drift_avoids_all_physical_boundaries": avoid == ALL_BOUNDARIES,
        "bulk_drift_forced_wall_set_empty": forced == (),
        "a6_matched_electron_ledger_absent": not mb.has_block(
            text, f"FVBCs/{a6.ELECTRON_BC}"
        ),
    }

    if sheath:
        checks.update(
            {
                "historical_thermal_material_absent": not mb.has_block(
                    text, f"FunctorMaterials/{a7.THERMAL_MATERIAL}"
                ),
                "historical_thermal_bc_absent": not mb.has_block(
                    text, f"FVBCs/{a7.THERMAL_BC}"
                ),
                "historical_thermal_pp_absent": not mb.has_block(
                    text, f"Postprocessors/{a7.THERMAL_PP}"
                ),
                "sheath_bc_present": mb.has_block(text, f"FVBCs/{SHEATH_BC}"),
                "sheath_type_exact": mp.get_parameter(
                    text, f"FVBCs/{SHEATH_BC}", "type"
                )
                == "PhysicsFVElectronGroundedSheathCollectionBC",
                "sheath_variable_ne": mp.get_parameter(
                    text, f"FVBCs/{SHEATH_BC}", "variable"
                )
                == "n_e",
                "sheath_wall_set_exact": words(
                    text, f"FVBCs/{SHEATH_BC}", "boundary"
                )
                == WALLS,
                "sheath_mean_energy_owner": mp.get_parameter(
                    text, f"FVBCs/{SHEATH_BC}", "mean_electron_energy"
                )
                == "mean_en",
                "sheath_potential_owner": mp.get_parameter(
                    text, f"FVBCs/{SHEATH_BC}", "potential"
                )
                == "potential_plasma",
                "sheath_pp_present": mb.has_block(text, f"Postprocessors/{SHEATH_PP}"),
            }
        )
    else:
        checks.update(
            {
                "historical_thermal_bc_present": mb.has_block(
                    text, f"FVBCs/{a7.THERMAL_BC}"
                ),
                "historical_thermal_factor_minus_one": float(
                    mp.get_parameter(text, f"FVBCs/{a7.THERMAL_BC}", "factor")
                    or "nan"
                )
                == -1.0,
                "sheath_bc_absent": not mb.has_block(text, f"FVBCs/{SHEATH_BC}"),
            }
        )

    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "boundaries_to_avoid": list(avoid),
        "boundaries_to_force": list(forced),
    }


def cpp_contract_audit() -> dict:
    source = CPP_SOURCE.read_text()
    checks = {
        "registered_object": "registerMooseObject(\"PhysicsApp\", PhysicsFVElectronGroundedSheathCollectionBC)"
        in source,
        "plasma_cell_state": "elemArg()" in source and "neighborArg()" in source,
        "face_arg_not_used_for_sheath_state": "singleSidedFaceArg" not in source,
        "grounded_repelling_branch_guard": "raw_phi_s_V < -negative_drop_tolerance_V"
        in source,
        "temperature_from_mean_energy": "(2.0 / 3.0) * mean_energy_eV" in source,
        "boltzmann_suppression": "exp(-effective_drop_V / electron_temperature_eV)"
        in source,
        "quarter_maxwellian_flux": "0.25 * n_e_hat * mean_speed_m_s * suppression"
        in source,
        "no_see_owner": "see_number_flux" not in source,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def analytic_contract_audit() -> dict:
    mean_energy_eV = 5.73276
    te_eV = (2.0 / 3.0) * mean_energy_eV
    mean_speed = math.sqrt(
        8.0 * ELEMENTARY_CHARGE_C * te_eV / (math.pi * ELECTRON_MASS_KG)
    )
    zero = math.exp(-0.0 / te_eV)
    ten = math.exp(-10.0 / te_eV)
    strong = math.exp(-100.0 / te_eV)
    wrong = math.exp(+10.0 / te_eV)
    checks = {
        "zero_drop_unsuppressed": math.isclose(zero, 1.0, rel_tol=0.0, abs_tol=0.0),
        "positive_drop_suppresses": 0.0 < ten < 1.0,
        "strong_drop_vanishes": strong < 1.0e-10,
        "wrong_sign_would_amplify": wrong > 1.0,
        "mean_speed_positive": mean_speed > 0.0,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "mean_energy_eV": mean_energy_eV,
        "electron_temperature_eV": te_eV,
        "mean_speed_m_s": mean_speed,
        "suppression_at_10V": ten,
        "suppression_at_100V": strong,
    }


def build_case(*, sheath: bool, dt: float) -> tuple[str, dict]:
    text, meta = a7._build_a7_case_input(
        BASE_TEXT, parameters=PARAMS, mode="combined_thermal"
    )
    primary_pp = a7.THERMAL_PP
    if sheath:
        text = replace_primary_wall_owner(text)
        primary_pp = SHEATH_PP
    text = instrument(text, dt=dt, primary_pp=primary_pp)
    text, promotion = _promote_current_acceptance_types(text)
    audit = construction_audit(text, sheath=sheath)
    if audit["status"] != "PASS":
        raise RuntimeError(f"construction audit failed: {audit}")
    return text, {
        "family": "sheath" if sheath else "control",
        "dt_s": dt,
        "end_time_s": TARGET_END,
        "primary_pp": primary_pp,
        "electron_reference_density_m3": float(meta["electron_reference_density_m3"]),
        "a7_meta": meta,
        "promotion": promotion,
        "audit": audit,
    }


def negative_controls() -> dict:
    duplicate_text, _ = a7._build_a7_case_input(
        BASE_TEXT, parameters=PARAMS, mode="combined_thermal"
    )
    wall_list = "'" + " ".join(WALLS) + "'"
    duplicate_text = mb.insert_child_block(
        duplicate_text,
        "FVBCs",
        f"""  [{SHEATH_BC}]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = n_e
    boundary = {wall_list}
    mean_electron_energy = mean_en
    potential = potential_plasma
  []""",
    )
    duplicate_text = mb.insert_child_block(
        duplicate_text,
        "Postprocessors",
        f"""  [{SHEATH_PP}]
    type = SideFVFluxBCIntegral
    boundary = {wall_list}
    fvbcs = '{SHEATH_BC}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    duplicate_text, _ = _promote_current_acceptance_types(duplicate_text)
    duplicate_audit = construction_audit(duplicate_text, sheath=True)

    forced_text, _ = build_case(sheath=True, dt=BASELINE_DT)
    forced_text = mp.upsert_parameter(
        forced_text, "FVKernels/n_e_drift", "boundaries_to_avoid", "'inlet outlet'"
    )
    forced_text = mp.upsert_parameter(
        forced_text,
        "FVKernels/n_e_drift",
        "boundaries_to_force",
        "'" + " ".join(WALLS) + "'",
    )
    forced_audit = construction_audit(forced_text, sheath=True)

    checks = {
        "duplicate_primary_owner_rejected": duplicate_audit["status"] == "FAIL",
        "forced_bulk_wall_drift_rejected": forced_audit["status"] == "FAIL",
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "duplicate_owner_audit": duplicate_audit,
        "forced_drift_audit": forced_audit,
    }


def self_test() -> dict:
    cpp = cpp_contract_audit()
    analytic = analytic_contract_audit()
    negative = negative_controls()
    control_text, control_meta = build_case(sheath=False, dt=BASELINE_DT)
    sheath_text, sheath_meta = build_case(sheath=True, dt=BASELINE_DT)
    checks = {
        "cpp_contract": cpp["status"] == "PASS",
        "analytic_contract": analytic["status"] == "PASS",
        "negative_controls": negative["status"] == "PASS",
        "control_construction": control_meta["audit"]["status"] == "PASS",
        "sheath_construction": sheath_meta["audit"]["status"] == "PASS",
        "semantic_difference_present": control_text != sheath_text,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "cpp": cpp,
        "analytic": analytic,
        "negative_controls": negative,
    }


def stage(name: str, text: str, meta: dict) -> dict:
    target = CASES / name
    staged = stage_case(
        SOURCE,
        target,
        input_text=text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    (target / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n"
    )
    return {"staging": staged, "meta": meta}


def read_rows(csv_path: Path) -> list[dict]:
    if not csv_path.is_file():
        return []
    with csv_path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(row: dict, name: str) -> float:
    return float(row[name])


def species_particle_rate(row: dict, species: str) -> float:
    cfg = a6.CHARGED[species]
    total_mass_rate = 0.0
    for wall in WALLS:
        _, _, surface_pp, migration_pp = a6._charged_names(species, wall)
        total_mass_rate += abs(as_float(row, surface_pp))
        total_mass_rate += abs(as_float(row, migration_pp))
    return total_mass_rate * AVOGADRO / float(cfg["molar_mass"])


def select_row(row: dict, *, primary_pp: str) -> dict:
    names = {
        "time",
        "n_e_inventory",
        "n_e_min",
        "n_e_max",
        "n_e_avg",
        "sum_w_min",
        "sum_w_max",
        "r31_charge_integral",
        "r31_gauss_flux_charge",
        "issue215_rho_q_min",
        "issue215_rho_q_max",
        "issue215_phi_min",
        "issue215_phi_max",
        primary_pp,
    }
    for species in a6.CHARGED:
        for wall in WALLS:
            _, _, surface_pp, migration_pp = a6._charged_names(species, wall)
            names.add(surface_pp)
            names.add(migration_pp)
    return {
        key: float(row[key])
        for key in sorted(names)
        if key in row and row[key] != ""
    }


def reconstruct_steps(rows: list[dict], *, n_ref: float, primary_pp: str) -> list[dict]:
    out = []
    for previous, current in zip(rows[:-1], rows[1:]):
        dt = as_float(current, "time") - as_float(previous, "time")
        if dt <= 0.0:
            continue
        primary_rate = abs(as_float(current, primary_pp)) * n_ref
        primary_loss = primary_rate * dt
        measured_electron_delta = (
            as_float(current, "n_e_inventory") - as_float(previous, "n_e_inventory")
        )
        electron_scale = max(abs(primary_loss), 1.0e-300)

        ion_rates = {
            species: species_particle_rate(current, species) for species in a6.CHARGED
        }
        ion_charge_delta = {
            species: -ELEMENTARY_CHARGE_C
            * int(a6.CHARGED[species]["charge"])
            * rate
            * dt
            for species, rate in ion_rates.items()
        }
        primary_charge_delta = ELEMENTARY_CHARGE_C * primary_loss
        expected_charge_delta = sum(ion_charge_delta.values()) + primary_charge_delta
        measured_charge_delta = (
            as_float(current, "r31_charge_integral")
            - as_float(previous, "r31_charge_integral")
        )
        charge_scale = max(
            sum(abs(v) for v in ion_charge_delta.values()) + abs(primary_charge_delta),
            1.0e-300,
        )
        gauss_delta = (
            (as_float(current, "r31_gauss_flux_charge") - as_float(current, "r31_charge_integral"))
            - (as_float(previous, "r31_gauss_flux_charge") - as_float(previous, "r31_charge_integral"))
        )
        out.append(
            {
                "t0_s": as_float(previous, "time"),
                "t1_s": as_float(current, "time"),
                "dt_s": dt,
                "primary_electron_particle_rate_s-1": primary_rate,
                "primary_electron_loss": primary_loss,
                "measured_electron_inventory_delta": measured_electron_delta,
                "electron_inventory_abs_defect_over_loss": abs(measured_electron_delta + primary_loss)
                / electron_scale,
                "ion_incident_particle_rate_s-1": ion_rates,
                "ion_charge_delta_C": ion_charge_delta,
                "primary_electron_charge_delta_C": primary_charge_delta,
                "expected_charge_delta_C": expected_charge_delta,
                "measured_charge_delta_C": measured_charge_delta,
                "charge_abs_defect_over_current_scale": abs(
                    measured_charge_delta - expected_charge_delta
                )
                / charge_scale,
                "gauss_residual_delta_C": gauss_delta,
                "gauss_abs_defect_over_current_scale": abs(gauss_delta) / charge_scale,
                "phi_min_V": as_float(current, "issue215_phi_min"),
                "phi_max_V": as_float(current, "issue215_phi_max"),
                "rho_q_min_C_m3": as_float(current, "issue215_rho_q_min"),
                "rho_q_max_C_m3": as_float(current, "issue215_rho_q_max"),
                "n_e_min_m3": as_float(current, "n_e_min"),
                "composition_max_abs_error": max(
                    abs(as_float(current, "sum_w_min") - 1.0),
                    abs(as_float(current, "sum_w_max") - 1.0),
                ),
            }
        )
    return out


def dt_label(dt: float) -> str:
    return f"{dt:.3e}".replace("+", "").replace("-", "m").replace(".", "p")


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    CASES.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    p0 = self_test()
    if p0["status"] != "PASS":
        raise RuntimeError(f"P0 self-test failed: {p0}")

    case_specs = []
    for dt in DTS:
        for sheath in (False, True):
            family = "sheath" if sheath else "control"
            name = f"{family}__dt_{dt_label(dt)}"
            text, meta = build_case(sheath=sheath, dt=dt)
            case_specs.append(
                {"name": name, "family": family, "dt_s": dt, "text": text, "meta": meta}
            )

    construction = {
        cfg["name"]: stage(cfg["name"], cfg["text"], cfg["meta"]) for cfg in case_specs
    }
    summary = {
        "issue": 215,
        "parent_controller": 211,
        "claim": "grounded_sheath_unresolved_particle_current_precursor",
        "repository_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "executable_realpath": str(EXE.resolve()),
        "executable_sha256": sha256(EXE),
        "baseline_dt_s": BASELINE_DT,
        "refined_dt_s": REFINED_DT,
        "equal_physical_end_time_s": TARGET_END,
        "p0": p0,
        "construction": construction,
        "cases": {},
        "equal_time_comparison": {},
        "status": "RUNNING",
        "scientific_disposition": "PENDING_EXECUTION",
    }

    for cfg in case_specs:
        name = cfg["name"]
        case_dir = CASES / name
        p2 = q0_run._p2(EXE, case_dir, LOGS / f"{name}_p2.log", 300.0)
        item = {
            "family": cfg["family"],
            "dt_s": cfg["dt_s"],
            "primary_pp": cfg["meta"]["primary_pp"],
            "p2": p2,
            "runtime": None,
            "classification": "P2_FAILURE" if p2["returncode"] != 0 else "P2_PASS",
            "rows": [],
            "step_metrics": [],
            "input_sha256": sha256(case_dir / "input.i"),
        }
        if p2["returncode"] == 0:
            runtime = q0_run._runtime(EXE, case_dir, LOGS / f"{name}_runtime.log", 1200.0)
            item["runtime"] = runtime
            csv_path = case_dir / "input_out.csv"
            rows = read_rows(csv_path)
            if csv_path.is_file():
                item["csv_sha256"] = sha256(csv_path)
            item["row_count"] = len(rows)
            item["rows"] = [select_row(row, primary_pp=cfg["meta"]["primary_pp"]) for row in rows]
            item["step_metrics"] = reconstruct_steps(
                rows,
                n_ref=float(cfg["meta"]["electron_reference_density_m3"]),
                primary_pp=cfg["meta"]["primary_pp"],
            )
            item["last_completed_time_s"] = (
                float(rows[-1]["time"])
                if rows and rows[-1].get("time") not in (None, "")
                else None
            )
            if runtime["returncode"] == 0 and item["last_completed_time_s"] is not None and math.isclose(
                item["last_completed_time_s"], TARGET_END, rel_tol=0.0, abs_tol=1.0e-18
            ):
                item["classification"] = "MEASURED_COMPLETE"
            elif runtime["returncode"] != 0:
                item["classification"] = "MEASURED_RUNTIME_FAILURE"
            else:
                item["classification"] = "INCOMPLETE_TIMELINE"
        summary["cases"][name] = item

    for dt in DTS:
        suffix = dt_label(dt)
        control = summary["cases"][f"control__dt_{suffix}"]
        sheath = summary["cases"][f"sheath__dt_{suffix}"]
        summary["equal_time_comparison"][f"{dt:.17g}"] = {
            "control_classification": control["classification"],
            "sheath_classification": sheath["classification"],
            "control_final": control["rows"][-1] if control["rows"] else {},
            "sheath_final": sheath["rows"][-1] if sheath["rows"] else {},
            "control_final_metrics": control["step_metrics"][-1] if control["step_metrics"] else None,
            "sheath_final_metrics": sheath["step_metrics"][-1] if sheath["step_metrics"] else None,
        }

    sheath_cases = [summary["cases"][f"sheath__dt_{dt_label(dt)}"] for dt in DTS]
    runtime_complete = all(c["classification"] == "MEASURED_COMPLETE" for c in sheath_cases)
    sheath_metrics = [m for case in sheath_cases for m in case["step_metrics"]]
    conservation_pass = bool(sheath_metrics) and all(
        m["electron_inventory_abs_defect_over_loss"] <= 1.0e-3
        and m["charge_abs_defect_over_current_scale"] <= 1.0e-3
        and m["gauss_abs_defect_over_current_scale"] <= 1.0e-3
        and m["composition_max_abs_error"] <= 1.0e-8
        and m["n_e_min_m3"] >= -1.0e-12
        for m in sheath_metrics
    )

    refined_consistency = False
    refinement = {}
    baseline_final = summary["cases"][f"sheath__dt_{dt_label(BASELINE_DT)}"]["step_metrics"]
    refined_final = summary["cases"][f"sheath__dt_{dt_label(REFINED_DT)}"]["step_metrics"]
    if baseline_final and refined_final:
        b = baseline_final[-1]
        r = refined_final[-1]
        current_rel = abs(
            b["primary_electron_particle_rate_s-1"] - r["primary_electron_particle_rate_s-1"]
        ) / max(abs(r["primary_electron_particle_rate_s-1"]), 1.0e-300)
        phi_rel = abs(b["phi_max_V"] - r["phi_max_V"]) / max(abs(r["phi_max_V"]), 1.0)
        refinement = {
            "primary_current_rate_relative_difference": current_rel,
            "phi_max_relative_difference": phi_rel,
        }
        refined_consistency = current_rel <= 5.0e-2 and phi_rel <= 5.0e-2

    causal_regulation = False
    base_cmp = summary["equal_time_comparison"][f"{BASELINE_DT:.17g}"]
    if base_cmp["control_final"] and base_cmp["sheath_final"]:
        control_phi = float(base_cmp["control_final"]["issue215_phi_max"])
        sheath_phi = float(base_cmp["sheath_final"]["issue215_phi_max"])
        control_rate = abs(float(base_cmp["control_final"][a7.THERMAL_PP]))
        sheath_rate = abs(float(base_cmp["sheath_final"][SHEATH_PP]))
        causal_regulation = sheath_rate < control_rate and abs(sheath_phi) < abs(control_phi)
        summary["baseline_regulation"] = {
            "control_phi_max_V": control_phi,
            "sheath_phi_max_V": sheath_phi,
            "control_primary_normalized_rate": control_rate,
            "sheath_primary_normalized_rate": sheath_rate,
            "primary_rate_reduced": sheath_rate < control_rate,
            "potential_magnitude_reduced": abs(sheath_phi) < abs(control_phi),
        }

    all_p2 = all(c["p2"]["returncode"] == 0 for c in summary["cases"].values())
    hard_pass = (
        p0["status"] == "PASS"
        and all_p2
        and runtime_complete
        and conservation_pass
        and refined_consistency
        and causal_regulation
    )
    summary["refinement"] = refinement
    summary["gates"] = {
        "G01_P0_contract_and_negative_controls": p0["status"] == "PASS",
        "G02_all_check_input": all_p2,
        "G03_sheath_runtime_complete": runtime_complete,
        "G04_sheath_particle_charge_gauss_closure": conservation_pass,
        "G05_timestep_refinement": refined_consistency,
        "G06_causal_collection_regulation": causal_regulation,
    }
    summary["scientific_hard_pass"] = hard_pass
    summary["scientific_disposition"] = (
        "W4_PARTICLE_CURRENT_PRECURSOR_PASS"
        if hard_pass
        else "W4_PARTICLE_CURRENT_PRECURSOR_NOT_ACCEPTED"
    )
    fingerprint = hashlib.sha256()
    for name in sorted(summary["cases"]):
        item = summary["cases"][name]
        fingerprint.update(name.encode())
        fingerprint.update(item.get("input_sha256", "").encode())
        fingerprint.update(item.get("csv_sha256", "").encode())
    summary["common_evidence_identity"] = (
        f"issue215-sheath-particle-{summary['repository_head'][:12]}-"
        f"{fingerprint.hexdigest()[:16]}"
    )
    summary["status"] = (
        "W4_PARTICLE_CURRENT_EVIDENCE_ACCEPTED"
        if hard_pass
        else "W4_PARTICLE_CURRENT_EVIDENCE_NOT_ACCEPTED"
    )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": summary["status"],
                "scientific_disposition": summary["scientific_disposition"],
                "common_evidence_identity": summary["common_evidence_identity"],
                "gates": summary["gates"],
                "refinement": refinement,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if not hard_pass:
        raise SystemExit(1)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
