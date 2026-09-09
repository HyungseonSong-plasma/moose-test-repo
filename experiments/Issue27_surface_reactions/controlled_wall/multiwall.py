#!/usr/bin/env python3
"""Run Issue #27 A1c O sticking on all plasma-facing walls of accepted R4-QF1."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue27_surface_reactions.controlled_wall.sticking import (
    A1B_FLUX_FUNCTOR,
    A1B_WALL_AREA_PP,
    A1B_WALL_RATE_PP,
    _build_sticking_case_input,
    _read_sticking_final_state,
)
from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue91_real_qvt_r3 import run as issue91_run
from physics_harness.evidence import create_collision_safe_directory, utc_timestamp, write_json_bundle
from physics_harness.execution.cases import stage_case
from physics_harness.execution.runtime import resolve_executable, validate_executable
from physics_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"

PLASMA_WALLS = (
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)
CASE_FACTORS: tuple[tuple[str, float], ...] = (("control", 0.0), ("sticking", -1.0))


class Issue27A1cError(RuntimeError):
    pass


def _validated_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    reaction_id = str(parameters.get("reaction_id", "O_to_half_O2"))
    if reaction_id != "O_to_half_O2":
        raise Issue27A1cError("A1c accepts only reaction_id='O_to_half_O2'")
    wall_model = str(parameters.get("wall_model", ""))
    if wall_model != "sticking_all_walls":
        raise Issue27A1cError("A1c requires wall_model='sticking_all_walls'")
    wall_scope = str(parameters.get("wall_scope", ""))
    if wall_scope != "all_plasma_walls":
        raise Issue27A1cError("A1c requires wall_scope='all_plasma_walls'")
    try:
        gamma = float(parameters.get("sticking_coefficient", 0.2))
    except (TypeError, ValueError) as exc:
        raise Issue27A1cError("sticking_coefficient must be numeric") from exc
    if not math.isfinite(gamma) or not 0.0 < gamma <= 1.0:
        raise Issue27A1cError("sticking_coefficient must lie in (0, 1]")
    motz = parameters.get("motz_wise_correction", False)
    if motz is not False:
        raise Issue27A1cError("A1c is frozen to Motz-Wise OFF")
    tg = str(parameters.get("gas_temperature_functor", "T_g"))
    if tg != "T_g":
        raise Issue27A1cError("A1c gas_temperature_functor is frozen to 'T_g'")
    return {
        "reaction_id": reaction_id,
        "wall_model": wall_model,
        "wall_scope": wall_scope,
        "wall_boundaries": list(PLASMA_WALLS),
        "sticking_coefficient": gamma,
        "motz_wise_correction": False,
        "gas_temperature_functor": tg,
    }


def _single_wall_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    frozen = _validated_parameters(parameters)
    return {
        "reaction_id": frozen["reaction_id"],
        "wall_model": "sticking",
        "wall_boundary": "plasma_wafer",
        "sticking_coefficient": frozen["sticking_coefficient"],
        "motz_wise_correction": False,
        "gas_temperature_functor": frozen["gas_temperature_functor"],
    }


def _build_multiwall_case_input(
    base_text: str,
    *,
    parameters: Mapping[str, Any],
    bc_factor: float,
) -> tuple[str, dict[str, Any]]:
    frozen = _validated_parameters(parameters)
    text, meta = _build_sticking_case_input(
        base_text,
        parameters=_single_wall_parameters(parameters),
        bc_factor=bc_factor,
    )
    wall_list = "'" + " ".join(PLASMA_WALLS) + "'"
    text = mp.upsert_parameter(
        text,
        "FVBCs/issue27_a1b_O_sticking_wall_flux",
        "boundary",
        wall_list,
    )
    text = mp.upsert_parameter(
        text,
        f"Postprocessors/{A1B_WALL_AREA_PP}",
        "boundary",
        wall_list,
    )
    text = mp.upsert_parameter(
        text,
        f"Postprocessors/{A1B_WALL_RATE_PP}",
        "boundary",
        wall_list,
    )
    meta["experiment"] = "A1C_R4_QF1_O_TO_HALF_O2_STICKING_ALL_WALLS"
    meta["wall_boundaries"] = list(PLASMA_WALLS)
    meta["excluded_boundaries"] = ["inlet", "outlet"]
    meta["surface_reaction"]["wall_model"] = "sticking_all_walls"
    meta["surface_reaction"]["wall_scope"] = "all_plasma_walls"
    meta["surface_reaction"]["wall_boundaries"] = list(PLASMA_WALLS)
    meta["validated_parameters"] = frozen
    return text, meta


def _stage_case(
    target: Path,
    *,
    parameters: Mapping[str, Any],
    bc_factor: float,
) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    input_text, meta = _build_multiwall_case_input(
        base,
        parameters=parameters,
        bc_factor=bc_factor,
    )
    staging = stage_case(
        SOURCE,
        target,
        input_text=input_text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    reference = float(
        meta["predecessor"]["predecessor"]["quasi_neutral_reference"][
            "electron_reference_density_m3"
        ]
    )
    expected_path = target / "expected.json"
    if expected_path.is_file():
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        expected["field_strength"] = 0.0
        expected["n0"] = reference
        expected_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
    (target / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "source": str(SOURCE.resolve()),
        "staging": staging,
        "construction": meta,
        "electron_reference_density_m3": reference,
    }


def _differential_evidence(states: Mapping[str, Mapping[str, Any]], parameters: Mapping[str, Any]) -> dict[str, Any]:
    frozen = _validated_parameters(parameters)
    if any(states[name].get("status") != "MEASURED" for name, _ in CASE_FACTORS):
        return {"status": "MISSING", "error": "one or more A1c states are not measured"}
    control = states["control"]
    sticking = states["sticking"]
    t0 = float(control["time"])
    t1 = float(sticking["time"])
    if t0 <= 0.0 or not math.isclose(t0, t1, rel_tol=0.0, abs_tol=1.0e-18):
        return {"status": "INVALID", "error": f"inconsistent final times: {t0}, {t1}"}
    area = float(sticking[A1B_WALL_AREA_PP])
    rate = float(sticking[A1B_WALL_RATE_PP])
    if area <= 0.0 or rate <= 0.0:
        return {"status": "INVALID", "error": f"invalid wall area/rate: {area}, {rate}"}
    expected_transfer = rate * t1
    scale = max(abs(expected_transfer), 1.0e-300)
    delta_o = float(sticking["mass_O"]) - float(control["mass_O"])
    delta_o2 = float(sticking["mass_O2"]) - float(control["mass_O2"])
    delta_total = float(sticking["mass_total"]) - float(control["mass_total"])
    delta_charge = float(sticking["r31_charge_integral"]) - float(control["r31_charge_integral"])
    return {
        "status": "MEASURED",
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "sticking_coefficient": frozen["sticking_coefficient"],
        "final_time_s": t1,
        "combined_wall_area_m2": area,
        "control_hypothetical_wall_mass_rate_kg_s": float(control[A1B_WALL_RATE_PP]),
        "sticking_applied_wall_mass_rate_kg_s": rate,
        "implicit_euler_expected_O_transfer_kg": expected_transfer,
        "delta_O_mass_vs_control_kg": delta_o,
        "delta_O2_mass_vs_control_kg": delta_o2,
        "delta_total_mass_vs_control_kg": delta_total,
        "delta_volume_charge_vs_control_C": delta_charge,
        "outward_O_loss_observed": delta_o < 0.0,
        "O_magnitude_relative_defect": abs(abs(delta_o) - expected_transfer) / scale,
        "O_O2_stoich_relative_defect": abs(delta_o + delta_o2) / scale,
        "total_mass_relative_to_surface_transfer": abs(delta_total) / scale,
        "nonnegative_mass_fractions": (
            float(sticking["w_O_min"]) >= -1.0e-12
            and float(sticking["w_O2_min"]) >= -1.0e-12
        ),
        "scientific_acceptance": "UNSET_EVIDENCE_ONLY",
    }


def run_multiwall_sticking(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue27A1cError("timeout must be positive")
    exe = resolve_executable(qpx)
    validate_executable(exe)
    frozen = _validated_parameters(parameters)
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue27_a1c_r4_qf1_o_sticking_all_walls_{stamp}",
    )
    cases_root = root / "cases"
    logs = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    staged: dict[str, Any] = {}
    for name, factor in CASE_FACTORS:
        staged[name] = _stage_case(
            cases_root / name,
            parameters=parameters,
            bc_factor=factor,
        )

    summary: dict[str, Any] = {
        "issue": 27,
        "experiment": "A1c_o_sticking_all_plasma_walls",
        "scientific_scope": "neutral O sticking expansion to all six plasma-facing walls",
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

    for name, _ in CASE_FACTORS:
        p2 = q0_run._p2(exe, cases_root / name, logs / f"a1c_{name}_p2.log", timeout)
        summary["p2"][name] = p2
        if p2["returncode"] != 0:
            summary["status"] = f"A1C_P2_FAIL_{name.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A1C_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 2

    states: dict[str, Mapping[str, Any]] = {}
    for name, _ in CASE_FACTORS:
        case_dir = cases_root / name
        runtime = q0_run._runtime(exe, case_dir, logs / f"a1c_{name}_runtime.log", timeout)
        state = _read_sticking_final_state(case_dir / "input_out.csv")
        summary["cases"][name] = {"runtime": runtime, "state": state}
        if runtime["returncode"] != 0:
            summary["status"] = f"A1C_RUNTIME_FAIL_{name.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A1C_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1
        states[name] = state

    evidence = _differential_evidence(states, parameters)
    summary["differential"] = evidence
    summary["status"] = (
        "A1C_ALL_WALL_EVIDENCE_READY_NOT_ACCEPTED"
        if evidence.get("status") == "MEASURED"
        else "A1C_EVIDENCE_MISSING"
    )
    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"ISSUE27_A1C_STATUS: {summary['status']}")
    if evidence.get("status") == "MEASURED":
        print(f"WALL_COUNT: {len(PLASMA_WALLS)}")
        print(f"COMBINED_WALL_AREA_M2: {evidence['combined_wall_area_m2']}")
        print(f"DELTA_O_KG: {evidence['delta_O_mass_vs_control_kg']}")
        print(f"O_MAGNITUDE_DEFECT: {evidence['O_magnitude_relative_defect']}")
        print(f"O_O2_STOICH_DEFECT: {evidence['O_O2_stoich_relative_defect']}")
    print(f"EVIDENCE_DIR: {root}")
    return 0 if evidence.get("status") == "MEASURED" else 1


__all__ = [
    "PLASMA_WALLS",
    "Issue27A1cError",
    "_build_multiwall_case_input",
    "_validated_parameters",
    "run_multiwall_sticking",
]
