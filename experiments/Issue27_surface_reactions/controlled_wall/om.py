#!/usr/bin/env python3
"""Run Issue #27 A2 prescribed O- -> O wall-neutralization control on R4-QF1."""
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue91_real_qvt_r3 import run as issue91_run
from qpx_harness.evidence import create_collision_safe_directory, utc_timestamp, write_json_bundle
from qpx_harness.execution.cases import stage_case
from qpx_harness.execution.runtime import resolve_executable, validate_executable
from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp
from experiments.historical_recipe_support.issue31_r4_qf1 import build_r4_qf1_input

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"

AVOGADRO = 6.02214076e23
ELEMENTARY_CHARGE_C = 1.602176634e-19
FARADAY_C_PER_MOL = AVOGADRO * ELEMENTARY_CHARGE_C
M_O_KG_PER_MOL = 0.016
PLASMA_WALLS = (
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)
CASE_MODES = ("control", "om_only")
AREA_PP = "issue27_a2_wall_area"
BC_OM = "issue27_a2_Om_wall_loss"
BC_O = "issue27_a2_O_wall_return"


class Issue27OmWallError(RuntimeError):
    pass


def _float_parameter(parameters: Mapping[str, Any], name: str, default: float) -> float:
    raw = parameters.get(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise Issue27OmWallError(f"parameters.{name} must be numeric") from exc
    if not math.isfinite(value):
        raise Issue27OmWallError(f"parameters.{name} must be finite")
    return value


def _validated_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    reaction_id = str(parameters.get("reaction_id", ""))
    if reaction_id != "Om_to_O":
        raise Issue27OmWallError("A2 requires reaction_id='Om_to_O'")
    wall_model = str(parameters.get("wall_model", ""))
    if wall_model != "om_prescribed_control":
        raise Issue27OmWallError("A2 requires wall_model='om_prescribed_control'")
    wall_scope = str(parameters.get("wall_scope", ""))
    if wall_scope != "all_plasma_walls":
        raise Issue27OmWallError("A2 requires wall_scope='all_plasma_walls'")
    see = _float_parameter(parameters, "secondary_emission_coefficient", 0.0)
    if see != 0.0:
        raise Issue27OmWallError("A2 is frozen to SEE=0")
    r_om = _float_parameter(parameters, "Om_event_flux_mol_m2_s", 5.0e-5)
    if r_om <= 0.0:
        raise Issue27OmWallError("Om_event_flux_mol_m2_s must be positive")
    return {
        "reaction_id": reaction_id,
        "wall_model": wall_model,
        "wall_scope": wall_scope,
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "secondary_emission_coefficient": 0.0,
        "Om_event_flux_mol_m2_s": r_om,
        "surface_reaction": "Om -> O",
        "electron_compensation": False,
        "production_sheath_kinetics": False,
    }


def _flux_contract(parameters: Mapping[str, Any]) -> dict[str, float]:
    frozen = _validated_parameters(parameters)
    r_om = float(frozen["Om_event_flux_mol_m2_s"])
    j_om = M_O_KG_PER_MOL * r_om
    return {
        "J_Om_out_kg_m2_s": j_om,
        "J_O_out_kg_m2_s": -j_om,
        "plasma_charge_rate_density_C_m2_s": FARADAY_C_PER_MOL * r_om,
    }


def _build_a2_case_input(
    base_text: str,
    *,
    parameters: Mapping[str, Any],
    mode: str,
) -> tuple[str, dict[str, Any]]:
    if mode not in CASE_MODES:
        raise Issue27OmWallError(f"unsupported A2 case mode {mode!r}")
    frozen = _validated_parameters(parameters)
    text, predecessor = build_r4_qf1_input(base_text)
    if predecessor["audit"]["status"] != "PASS":
        raise Issue27OmWallError("R4-QF1 predecessor audit is not PASS")

    flux = _flux_contract(parameters)
    wall_list = "'" + " ".join(PLASMA_WALLS) + "'"
    for path in (f"FVBCs/{BC_OM}", f"FVBCs/{BC_O}"):
        mb.require_absent(text, path)
    mb.require_absent(text, f"Postprocessors/{AREA_PP}")

    reaction_on = mode == "om_only"
    om_value = -flux["J_Om_out_kg_m2_s"] if reaction_on else 0.0
    # O is returned from the wall into the plasma, so J_O,out < 0.  A1 froze
    # FVNeumannBC.value = -J_out, hence this BC value is positive.
    o_value = -flux["J_O_out_kg_m2_s"] if reaction_on else 0.0

    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{BC_OM}]
    type = FVNeumannBC
    variable = w_Om
    boundary = {wall_list}
    value = {om_value:.17g}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{BC_O}]
    type = FVNeumannBC
    variable = w_O
    boundary = {wall_list}
    value = {o_value:.17g}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{AREA_PP}]
    type = AreaPostprocessor
    boundary = {wall_list}
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    for pp in (
        "mass_total",
        "mass_O",
        "mass_Om",
        "w_O_min",
        "w_Om_min",
        "n_e_inventory",
        "n_e_min",
        "r31_charge_integral",
        "r31_gauss_flux_charge",
    ):
        text = mp.upsert_parameter(
            text,
            f"Postprocessors/{pp}",
            "execute_on",
            "'INITIAL TIMESTEP_END'",
        )

    return text, {
        "issue": 27,
        "experiment": "A2_R4_QF1_OM_TO_O_WALL_NEUTRALIZATION",
        "mode": mode,
        "predecessor": predecessor,
        "validated_parameters": frozen,
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "physical_flux_contract": flux,
        "moose_bc_values": {"Om": om_value, "O": o_value},
        "sign_contract": "physical outward positive -> FVNeumannBC value = -physical outward flux",
        "charge_contract": (
            "Om wall loss removes one negative elementary charge from plasma per event; "
            "expected DeltaQ_volume = +F*R_Om*A_wall*dt; no plasma electron is created"
        ),
        "frozen_phase": {
            "R4_QF1_preserved": True,
            "volumetric_reactions": False,
            "secondary_emission": False,
            "electron_wall_compensation": False,
            "surface_accumulated_charge": False,
            "production_sheath_kinetics": False,
        },
    }


def _stage_case(
    target: Path,
    *,
    parameters: Mapping[str, Any],
    mode: str,
) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    input_text, meta = _build_a2_case_input(base, parameters=parameters, mode=mode)
    staging = stage_case(
        SOURCE,
        target,
        input_text=input_text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    (target / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "source": str(SOURCE.resolve()),
        "staging": staging,
        "construction": meta,
    }


def _read_final_state(csv_path: Path) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        return {"status": "MISSING", "error": "need INITIAL and TIMESTEP_END rows"}
    required = (
        "time",
        AREA_PP,
        "mass_total",
        "mass_O",
        "mass_Om",
        "w_O_min",
        "w_Om_min",
        "n_e_inventory",
        "n_e_min",
        "r31_charge_integral",
        "r31_gauss_flux_charge",
    )
    row = rows[-1]
    missing = [name for name in required if name not in row]
    if missing:
        return {"status": "MISSING", "error": f"missing CSV columns: {missing}"}
    try:
        values = {name: float(row[name]) for name in required}
    except (TypeError, ValueError) as exc:
        return {"status": "INVALID", "error": str(exc)}
    if not all(math.isfinite(value) for value in values.values()):
        return {"status": "INVALID", "error": "non-finite final-state value"}
    return {"status": "MEASURED", **values}


def _rel_defect(measured: float, expected: float) -> float:
    return abs(measured - expected) / max(abs(expected), 1.0e-300)


def _differential_evidence(
    states: Mapping[str, Mapping[str, Any]],
    *,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    if any(states[name].get("status") != "MEASURED" for name in CASE_MODES):
        return {"status": "MISSING", "error": "one or more A2 states are not measured"}
    frozen = _validated_parameters(parameters)
    flux = _flux_contract(parameters)
    control = states["control"]
    om_only = states["om_only"]

    dt_control = float(control["time"])
    dt_om = float(om_only["time"])
    if dt_control <= 0.0 or not math.isclose(dt_control, dt_om, rel_tol=0.0, abs_tol=1.0e-18):
        return {"status": "INVALID", "error": f"inconsistent final times: {[dt_control, dt_om]}"}
    dt = dt_control
    area_control = float(control[AREA_PP])
    area_om = float(om_only[AREA_PP])
    if area_control <= 0.0 or not math.isclose(area_control, area_om, rel_tol=1.0e-12, abs_tol=0.0):
        return {"status": "INVALID", "error": f"inconsistent wall areas: {[area_control, area_om]}"}
    area = area_control

    expected_om_loss = -flux["J_Om_out_kg_m2_s"] * area * dt
    expected_o_return = -flux["J_O_out_kg_m2_s"] * area * dt
    expected_delta_q = flux["plasma_charge_rate_density_C_m2_s"] * area * dt

    def delta(key: str) -> float:
        return float(om_only[key]) - float(control[key])

    measured = {
        "delta_mass_Om_kg": delta("mass_Om"),
        "delta_mass_O_kg": delta("mass_O"),
        "delta_mass_total_kg": delta("mass_total"),
        "delta_charge_C": delta("r31_charge_integral"),
        "delta_electron_inventory": delta("n_e_inventory"),
    }
    gauss_defect = float(om_only["r31_gauss_flux_charge"]) - float(
        om_only["r31_charge_integral"]
    )
    transfer_scale = max(abs(expected_om_loss), 1.0e-300)
    charge_scale = max(abs(expected_delta_q), 1.0e-300)

    return {
        "status": "MEASURED",
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "final_time_s": dt,
        "combined_wall_area_m2": area,
        "parameters": frozen,
        "flux_contract": flux,
        "expected": {
            "delta_mass_Om_kg": expected_om_loss,
            "delta_mass_O_kg": expected_o_return,
            "delta_charge_C": expected_delta_q,
            "charge_sign": "positive",
        },
        "measured_delta_vs_control": measured,
        "Om_mass_relative_defect": _rel_defect(measured["delta_mass_Om_kg"], expected_om_loss),
        "O_return_relative_defect": _rel_defect(measured["delta_mass_O_kg"], expected_o_return),
        "total_mass_relative_to_transfer": abs(measured["delta_mass_total_kg"]) / transfer_scale,
        "charge_relative_defect": _rel_defect(measured["delta_charge_C"], expected_delta_q),
        "positive_volume_charge_shift": measured["delta_charge_C"] > 0.0,
        "electron_inventory_relative_to_charge_scale": (
            abs(measured["delta_electron_inventory"] * ELEMENTARY_CHARGE_C) / charge_scale
        ),
        "gauss_defect_C": gauss_defect,
        "nonnegative_state": all(
            float(om_only[key]) >= -1.0e-12
            for key in ("w_O_min", "w_Om_min", "n_e_min")
        ),
        "scientific_acceptance": "UNSET_EVIDENCE_ONLY",
        "interpretation_contract": (
            "A2 isolates Om -> O.  Om loss must produce a positive plasma-volume charge shift; "
            "electron compensation and global wall-current closure are deliberately deferred to A3e."
        ),
    }


def run_om_wall_control(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue27OmWallError("timeout must be positive")
    exe = resolve_executable(qpx)
    validate_executable(exe)
    frozen = _validated_parameters(parameters)
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue27_a2_r4_qf1_om_wall_neutralization_{stamp}",
    )
    cases_root = root / "cases"
    logs = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    staged: dict[str, Any] = {}
    for mode in CASE_MODES:
        staged[mode] = _stage_case(
            cases_root / mode,
            parameters=parameters,
            mode=mode,
        )

    summary: dict[str, Any] = {
        "issue": 27,
        "experiment": "A2_om_wall_neutralization",
        "scientific_scope": (
            "prescribed Om -> O neutralization on all six plasma-facing walls; "
            "negative-ion charge-removal control only, with SEE and electron compensation OFF"
        ),
        "repository_head": issue91_run._repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": issue91_run._sha256(exe),
        "parameters": frozen,
        "staged": staged,
        "p2": {},
        "cases": {},
        "differential": {},
        "status": "NOT_RUN",
    }

    for mode in CASE_MODES:
        p2 = q0_run._p2(exe, cases_root / mode, logs / f"a2_{mode}_p2.log", timeout)
        summary["p2"][mode] = p2
        if p2["returncode"] != 0:
            summary["status"] = f"A2_P2_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A2_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 2

    states: dict[str, Mapping[str, Any]] = {}
    for mode in CASE_MODES:
        case_dir = cases_root / mode
        runtime = q0_run._runtime(exe, case_dir, logs / f"a2_{mode}_runtime.log", timeout)
        state = _read_final_state(case_dir / "input_out.csv")
        summary["cases"][mode] = {"runtime": runtime, "state": state}
        if runtime["returncode"] != 0:
            summary["status"] = f"A2_RUNTIME_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A2_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1
        states[mode] = state

    evidence = _differential_evidence(states, parameters=parameters)
    summary["differential"] = evidence
    summary["status"] = (
        "A2_OM_CHARGE_SHIFT_EVIDENCE_READY_NOT_ACCEPTED"
        if evidence.get("status") == "MEASURED"
        else "A2_EVIDENCE_MISSING"
    )
    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"ISSUE27_A2_STATUS: {summary['status']}")
    if evidence.get("status") == "MEASURED":
        print(f"WALL_COUNT: {len(PLASMA_WALLS)}")
        print(f"COMBINED_WALL_AREA_M2: {evidence['combined_wall_area_m2']}")
        print(f"EXPECTED_DELTA_Q_C: {evidence['expected']['delta_charge_C']}")
        print(f"MEASURED_DELTA_Q_C: {evidence['measured_delta_vs_control']['delta_charge_C']}")
        print(f"CHARGE_RELATIVE_DEFECT: {evidence['charge_relative_defect']}")
        print(f"POSITIVE_VOLUME_CHARGE_SHIFT: {evidence['positive_volume_charge_shift']}")
        print(f"GAUSS_DEFECT_C: {evidence['gauss_defect_C']}")
    print(f"EVIDENCE_DIR: {root}")
    return 0 if evidence.get("status") == "MEASURED" else 1


__all__ = [
    "Issue27OmWallError",
    "_build_a2_case_input",
    "_differential_evidence",
    "_flux_contract",
    "_validated_parameters",
    "run_om_wall_control",
]
