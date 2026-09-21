import csv
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from experiments.Issue27_surface_reactions.controlled_wall import electron_wall as a7
from experiments.Issue27_surface_reactions.controlled_wall.combined import PLASMA_WALLS
from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue193_a8_see_acceptance.run import _promote_current_acceptance_types
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import stage_case

ROOT = Path("/workspace")
OUT = ROOT / "issue213-wall-drift-results"
CASES = OUT / "cases"
LOGS = OUT / "logs"
SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0"
EXE = ROOT / "physics_app/physics-opt"
ELEMENTARY_CHARGE_C = 1.602176634e-19
BASELINE_DT = 1.0e-10
REFINED_DT = 5.0e-11
TARGET_END = 2.0e-10
DTS = (BASELINE_DT, REFINED_DT)
WALLS = tuple(PLASMA_WALLS)
ALL_BOUNDARIES = ("inlet", "outlet", *WALLS)
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


def instrument(text: str, *, dt: float) -> str:
    text = mp.upsert_parameter(text, "Executioner", "dt", f"{dt:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{TARGET_END:.17g}")
    for pp in (
        "n_e_inventory",
        "n_e_min",
        "n_e_max",
        "n_e_avg",
        "r31_charge_integral",
        "r31_gauss_flux_charge",
        a7.THERMAL_PP,
    ):
        if mb.has_block(text, f"Postprocessors/{pp}"):
            text = mp.upsert_parameter(
                text, f"Postprocessors/{pp}", "execute_on", "'INITIAL TIMESTEP_END'"
            )
    text = add_pp(
        text,
        "issue213_rho_q_min",
        "    type = ADElementExtremeFunctorValue\n"
        "    functor = charge_density\n"
        "    value_type = min\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    text = add_pp(
        text,
        "issue213_rho_q_max",
        "    type = ADElementExtremeFunctorValue\n"
        "    functor = charge_density\n"
        "    value_type = max\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    text = add_pp(
        text,
        "issue213_phi_min",
        "    type = ElementExtremeValue\n"
        "    variable = potential_plasma\n"
        "    value_type = min\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    text = add_pp(
        text,
        "issue213_phi_max",
        "    type = ElementExtremeValue\n"
        "    variable = potential_plasma\n"
        "    value_type = max\n"
        "    block = plasma\n"
        "    execute_on = 'INITIAL TIMESTEP_END'",
    )
    return text


def configure_wall_drift(text: str, *, enabled: bool, negative_control: bool = False) -> str:
    path = "FVKernels/n_e_drift"
    if not mb.has_block(text, path):
        raise RuntimeError("missing FVKernels/n_e_drift")
    if enabled:
        forced = WALLS[:-1] if negative_control else WALLS
        text = mp.upsert_parameter(text, path, "boundaries_to_avoid", "'inlet outlet'")
        text = mp.upsert_parameter(
            text, path, "boundaries_to_force", "'" + " ".join(forced) + "'"
        )
    return text


def construction_audit(text: str, *, wall_drift: bool) -> dict:
    drift_path = "FVKernels/n_e_drift"
    thermal_path = f"FVBCs/{a7.THERMAL_BC}"
    avoid = words(text, drift_path, "boundaries_to_avoid")
    forced = words(text, drift_path, "boundaries_to_force")
    checks = {
        "current_drift_type": mp.get_parameter(text, drift_path, "type")
        == "PhysicsFVElectrostaticDrift",
        "electron_charge_number_minus_one": float(
            mp.get_parameter(text, drift_path, "charge_number") or "nan"
        )
        == -1.0,
        "solved_potential_owned": mp.get_parameter(text, drift_path, "potential")
        == "potential_plasma",
        "thermal_bc_present": mb.has_block(text, thermal_path),
        "thermal_factor_minus_one": float(
            mp.get_parameter(text, thermal_path, "factor") or "nan"
        )
        == -1.0,
        "thermal_wall_set_exact": words(text, thermal_path, "boundary") == WALLS,
    }
    if wall_drift:
        checks.update(
            {
                "drift_avoid_only_inlet_outlet": avoid == ("inlet", "outlet"),
                "forced_wall_set_exact": forced == WALLS,
            }
        )
    else:
        checks.update(
            {
                "drift_avoid_all_physical_boundaries": avoid == ALL_BOUNDARIES,
                "forced_wall_set_empty": forced == (),
            }
        )
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "boundaries_to_avoid": list(avoid),
        "boundaries_to_force": list(forced),
    }


def build_case(*, wall_drift: bool, dt: float) -> tuple[str, dict]:
    text, meta = a7._build_a7_case_input(
        BASE_TEXT, parameters=PARAMS, mode="electron_thermal_only"
    )
    text = configure_wall_drift(text, enabled=wall_drift)
    text = instrument(text, dt=dt)
    text, promotion = _promote_current_acceptance_types(text)
    audit = construction_audit(text, wall_drift=wall_drift)
    if audit["status"] != "PASS":
        raise RuntimeError(f"construction audit failed: {audit}")
    return text, {
        "wall_drift_enabled": wall_drift,
        "dt_s": dt,
        "end_time_s": TARGET_END,
        "a7_meta": meta,
        "promotion": promotion,
        "audit": audit,
    }


def negative_control() -> dict:
    text, _ = a7._build_a7_case_input(
        BASE_TEXT, parameters=PARAMS, mode="electron_thermal_only"
    )
    text = configure_wall_drift(text, enabled=True, negative_control=True)
    text = instrument(text, dt=BASELINE_DT)
    text, _ = _promote_current_acceptance_types(text)
    audit = construction_audit(text, wall_drift=True)
    return {
        "status": "PASS" if audit["status"] == "FAIL" else "FAIL",
        "expected": "construction audit rejects incomplete forced-wall ownership",
        "observed_audit": audit,
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


def selected_row(row: dict) -> dict:
    keys = (
        "time",
        "n_e_inventory",
        "n_e_min",
        "n_e_max",
        "n_e_avg",
        "r31_charge_integral",
        "r31_gauss_flux_charge",
        a7.THERMAL_PP,
        "issue213_rho_q_min",
        "issue213_rho_q_max",
        "issue213_phi_min",
        "issue213_phi_max",
    )
    out = {}
    for key in keys:
        if key in row and row[key] != "":
            out[key] = float(row[key])
    return out


def runtime_log_evidence(log_path: Path) -> dict:
    if not log_path.is_file():
        return {"status": "MISSING"}
    text = log_path.read_text(errors="replace")
    steps = [
        {
            "step": int(m.group(1)),
            "time_s": float(m.group(2)),
            "dt_s": float(m.group(3)) if m.group(3) else None,
        }
        for m in re.finditer(
            r"Time Step\s+(\d+),\s*time\s*=\s*([0-9.eE+\-]+)(?:,\s*dt\s*=\s*([0-9.eE+\-]+))?",
            text,
        )
    ]
    negative_density = None
    match = re.search(
        r"requires electron_number_density\s*>=\s*0.*?Got\s+(-?[0-9.eE+\-]+)",
        text,
        flags=re.DOTALL,
    )
    if match:
        negative_density = float(match.group(1))
    return {
        "status": "MEASURED",
        "steps": steps,
        "negative_electron_density_iterate_m3": negative_density,
    }


def reconstruct_steps(rows: list[dict], *, n_ref: float) -> list[dict]:
    out = []
    if len(rows) < 2:
        return out
    for previous, current in zip(rows[:-1], rows[1:]):
        t0 = as_float(previous, "time")
        t1 = as_float(current, "time")
        dt = t1 - t0
        if dt <= 0:
            continue
        delta_ne = as_float(current, "n_e_inventory") - as_float(previous, "n_e_inventory")
        thermal_rate_norm = abs(as_float(current, a7.THERMAL_PP))
        thermal_rate = thermal_rate_norm * n_ref
        thermal_loss = thermal_rate * dt
        drift_loss = -delta_ne - thermal_loss
        drift_rate = drift_loss / dt
        expected_charge_delta = ELEMENTARY_CHARGE_C * (thermal_loss + drift_loss)
        measured_charge_delta = (
            as_float(current, "r31_charge_integral")
            - as_float(previous, "r31_charge_integral")
        )
        current_scale = max(
            ELEMENTARY_CHARGE_C * (abs(thermal_loss) + abs(drift_loss)), 1.0e-300
        )
        gauss_defect = (
            as_float(current, "r31_gauss_flux_charge")
            - as_float(current, "r31_charge_integral")
        )
        out.append(
            {
                "t0_s": t0,
                "t1_s": t1,
                "dt_s": dt,
                "measured_electron_inventory_delta": delta_ne,
                "thermal_particle_rate_s-1": thermal_rate,
                "thermal_electron_loss": thermal_loss,
                "reconstructed_wall_drift_particle_rate_s-1": drift_rate,
                "reconstructed_wall_drift_electron_loss": drift_loss,
                "reconstructed_wall_drift_charge_current_A": ELEMENTARY_CHARGE_C
                * drift_rate,
                "expected_charge_delta_C": expected_charge_delta,
                "measured_charge_delta_C": measured_charge_delta,
                "charge_abs_defect_over_current_scale": abs(
                    measured_charge_delta - expected_charge_delta
                )
                / current_scale,
                "gauss_residual_C": gauss_defect,
                "gauss_abs_defect_over_current_scale": abs(gauss_defect)
                / current_scale,
                "phi_min_V": as_float(current, "issue213_phi_min"),
                "phi_max_V": as_float(current, "issue213_phi_max"),
                "rho_q_min_C_m3": as_float(current, "issue213_rho_q_min"),
                "rho_q_max_C_m3": as_float(current, "issue213_rho_q_max"),
                "n_e_min": as_float(current, "n_e_min"),
            }
        )
    return out


def dt_label(dt: float) -> str:
    return f"{dt:.3e}".replace("+", "").replace("-", "m").replace(".", "p")


CASES.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

neg = negative_control()
if neg["status"] != "PASS":
    raise RuntimeError(f"negative ownership checker control failed: {neg}")

case_specs = []
for dt in DTS:
    for wall_drift in (False, True):
        family = "wall_drift" if wall_drift else "control"
        name = f"{family}__dt_{dt_label(dt)}"
        text, meta = build_case(wall_drift=wall_drift, dt=dt)
        case_specs.append(
            {
                "name": name,
                "family": family,
                "dt_s": dt,
                "text": text,
                "meta": meta,
            }
        )

construction = {
    cfg["name"]: stage(cfg["name"], cfg["text"], cfg["meta"]) for cfg in case_specs
}

summary = {
    "issue": 213,
    "parent_controller": 211,
    "repository_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "executable_realpath": str(EXE.resolve()),
    "executable_sha256": sha256(EXE),
    "baseline_dt_s": BASELINE_DT,
    "refined_dt_s": REFINED_DT,
    "equal_physical_end_time_s": TARGET_END,
    "negative_control": neg,
    "construction": construction,
    "cases": {},
    "equal_time_comparison": {},
    "scientific_disposition": "PENDING_EXECUTION",
    "status": "RUNNING",
}

capture_complete = True
for cfg in case_specs:
    name = cfg["name"]
    case_dir = CASES / name
    p2_log = LOGS / f"{name}_p2.log"
    runtime_log = LOGS / f"{name}_runtime.log"
    p2 = q0_run._p2(EXE, case_dir, p2_log, 300.0)
    item = {
        "family": cfg["family"],
        "dt_s": cfg["dt_s"],
        "input_sha256": sha256(case_dir / "input.i"),
        "p2": p2,
        "runtime": None,
        "runtime_log_evidence": None,
        "rows": [],
        "reconstructed_steps": [],
    }
    if p2["returncode"] != 0:
        item["classification"] = "P2_CONSTRUCTION_FAIL"
        capture_complete = False
        summary["cases"][name] = item
        continue

    runtime = q0_run._runtime(EXE, case_dir, runtime_log, 1200.0)
    item["runtime"] = runtime
    item["runtime_log_evidence"] = runtime_log_evidence(runtime_log)
    rows = read_rows(case_dir / "input_out.csv")
    item["rows"] = [selected_row(row) for row in rows]
    n_ref = float(cfg["meta"]["a7_meta"]["electron_reference_density_m3"])
    item["reconstructed_steps"] = reconstruct_steps(rows, n_ref=n_ref)
    item["last_completed_time_s"] = (
        float(rows[-1]["time"]) if rows and rows[-1].get("time") not in (None, "") else None
    )
    if rows and (case_dir / "input_out.csv").is_file():
        item["csv_sha256"] = sha256(case_dir / "input_out.csv")

    if not rows:
        item["classification"] = "NO_RUNTIME_TIMELINE"
        capture_complete = False
    elif runtime["returncode"] == 0 and math.isclose(
        item["last_completed_time_s"], TARGET_END, rel_tol=0.0, abs_tol=1.0e-18
    ):
        item["classification"] = "MEASURED_COMPLETE"
    elif runtime["returncode"] != 0:
        item["classification"] = "MEASURED_RUNTIME_FAILURE"
    else:
        item["classification"] = "INCOMPLETE_TIMELINE"
        capture_complete = False
    summary["cases"][name] = item

for dt in DTS:
    label = f"{dt:.17g}"
    control_name = f"control__dt_{dt_label(dt)}"
    drift_name = f"wall_drift__dt_{dt_label(dt)}"
    control = summary["cases"][control_name]
    drift = summary["cases"][drift_name]
    comparison = {
        "control_case": control_name,
        "wall_drift_case": drift_name,
        "control_classification": control["classification"],
        "wall_drift_classification": drift["classification"],
    }
    if control["rows"] and drift["rows"]:
        c_final = control["rows"][-1]
        d_final = drift["rows"][-1]
        if "issue213_phi_max" in c_final and "issue213_phi_max" in d_final:
            comparison["phi_max_control_V"] = c_final["issue213_phi_max"]
            comparison["phi_max_wall_drift_V"] = d_final["issue213_phi_max"]
            comparison["phi_max_change_V"] = (
                d_final["issue213_phi_max"] - c_final["issue213_phi_max"]
            )
        if control["reconstructed_steps"] and drift["reconstructed_steps"]:
            comparison["control_last_step"] = control["reconstructed_steps"][-1]
            comparison["wall_drift_last_step"] = drift["reconstructed_steps"][-1]
    summary["equal_time_comparison"][label] = comparison

baseline_drift = summary["cases"][f"wall_drift__dt_{dt_label(BASELINE_DT)}"]
refined_drift = summary["cases"][f"wall_drift__dt_{dt_label(REFINED_DT)}"]
complete_drift_steps = [
    step
    for item in (baseline_drift, refined_drift)
    for step in item.get("reconstructed_steps", [])
]
finite_reconstruction = bool(complete_drift_steps) and all(
    math.isfinite(step["reconstructed_wall_drift_particle_rate_s-1"])
    and math.isfinite(step["charge_abs_defect_over_current_scale"])
    for step in complete_drift_steps
)
charge_closed = bool(complete_drift_steps) and all(
    step["charge_abs_defect_over_current_scale"] <= 1.0e-3
    for step in complete_drift_steps
)

if not capture_complete:
    summary["status"] = "ISSUE213_EVIDENCE_PARTIAL"
    summary["scientific_disposition"] = "CONSTRUCTION_OR_RUNTIME_REVIEW_REQUIRED"
elif finite_reconstruction and charge_closed:
    summary["status"] = "ISSUE213_DISCRIMINATOR_EVIDENCE_CAPTURED"
    summary["scientific_disposition"] = "READY_FOR_W2_CAUSAL_INTERPRETATION"
else:
    summary["status"] = "ISSUE213_DISCRIMINATOR_RECONSTRUCTION_FAIL"
    summary["scientific_disposition"] = "REVIEW_ACCOUNTING_BEFORE_INTERPRETATION"

fingerprint = hashlib.sha256()
for name in sorted(summary["cases"]):
    item = summary["cases"][name]
    fingerprint.update(name.encode())
    fingerprint.update(item.get("input_sha256", "").encode())
    fingerprint.update(item.get("csv_sha256", "").encode())
summary["evidence_identity"] = (
    f"issue213-wall-drift-{summary['repository_head'][:12]}-{fingerprint.hexdigest()[:16]}"
)

(OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(
    json.dumps(
        {
            "status": summary["status"],
            "scientific_disposition": summary["scientific_disposition"],
            "evidence_identity": summary["evidence_identity"],
            "cases": {
                name: {
                    "classification": item["classification"],
                    "runtime_returncode": item["runtime"]["returncode"]
                    if item["runtime"]
                    else None,
                    "last_completed_time_s": item.get("last_completed_time_s"),
                }
                for name, item in summary["cases"].items()
            },
        },
        indent=2,
        sort_keys=True,
    )
)
