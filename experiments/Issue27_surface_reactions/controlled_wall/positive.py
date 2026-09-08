#!/usr/bin/env python3
"""Run Issue #27 A3 prescribed O2+/O+ wall-neutralization controls on R4-QF1."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue91_real_qvt_r3 import run as issue91_run
from qpx_harness.evidence import create_collision_safe_directory, utc_timestamp, write_json_bundle
from qpx_harness.execution.cases import stage_case
from qpx_harness.execution.runtime import resolve_executable, validate_executable
from qpx_harness.adapters.moose import blocks as mb
from qpx_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue31_r4_qf1 import build_r4_qf1_input

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"

AVOGADRO = 6.02214076e23
ELEMENTARY_CHARGE_C = 1.602176634e-19
FARADAY_C_PER_MOL = AVOGADRO * ELEMENTARY_CHARGE_C
M_O2_KG_PER_MOL = 0.032
M_O_KG_PER_MOL = 0.016
PLASMA_WALLS = (
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)
CASE_MODES = ("control", "o2p_only", "op_only")
AREA_PP = "issue27_a3_wall_area"
BC_O2P = "issue27_a3_O2p_wall_loss"
BC_OP = "issue27_a3_Op_wall_loss"
BC_O = "issue27_a3_O_wall_return"


class Issue27PositiveIonWallError(RuntimeError):
    pass


def _float_parameter(parameters: Mapping[str, Any], name: str, default: float) -> float:
    raw = parameters.get(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise Issue27PositiveIonWallError(f"parameters.{name} must be numeric") from exc
    if not math.isfinite(value):
        raise Issue27PositiveIonWallError(f"parameters.{name} must be finite")
    return value


def _validated_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    wall_model = str(parameters.get("wall_model", ""))
    if wall_model != "positive_ion_prescribed_control":
        raise Issue27PositiveIonWallError(
            "A3 requires wall_model='positive_ion_prescribed_control'"
        )
    wall_scope = str(parameters.get("wall_scope", ""))
    if wall_scope != "all_plasma_walls":
        raise Issue27PositiveIonWallError("A3 requires wall_scope='all_plasma_walls'")
    see = _float_parameter(parameters, "secondary_emission_coefficient", 0.0)
    if see != 0.0:
        raise Issue27PositiveIonWallError("A3 is frozen to SEE=0")

    r_o2p = _float_parameter(parameters, "O2p_event_flux_mol_m2_s", 1.0e-4)
    r_op = _float_parameter(parameters, "Op_event_flux_mol_m2_s", 1.0e-4)
    if min(r_o2p, r_op) <= 0.0:
        raise Issue27PositiveIonWallError("positive-ion event fluxes must be positive")

    return {
        "wall_model": wall_model,
        "wall_scope": wall_scope,
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "secondary_emission_coefficient": 0.0,
        "O2p_event_flux_mol_m2_s": r_o2p,
        "Op_event_flux_mol_m2_s": r_op,
        "surface_reactions": ["O2p -> constrained O2", "Op -> O"],
        "electron_compensation": False,
        "production_sheath_kinetics": False,
    }


def _flux_contract(parameters: Mapping[str, Any]) -> dict[str, float]:
    frozen = _validated_parameters(parameters)
    r_o2p = float(frozen["O2p_event_flux_mol_m2_s"])
    r_op = float(frozen["Op_event_flux_mol_m2_s"])
    return {
        "J_O2p_out_kg_m2_s": M_O2_KG_PER_MOL * r_o2p,
        "J_Op_out_kg_m2_s": M_O_KG_PER_MOL * r_op,
        "J_O_return_for_Op_out_kg_m2_s": -M_O_KG_PER_MOL * r_op,
        "O2p_plasma_charge_rate_density_C_m2_s": -FARADAY_C_PER_MOL * r_o2p,
        "Op_plasma_charge_rate_density_C_m2_s": -FARADAY_C_PER_MOL * r_op,
    }


def _build_a3_case_input(
    base_text: str,
    *,
    parameters: Mapping[str, Any],
    mode: str,
) -> tuple[str, dict[str, Any]]:
    if mode not in CASE_MODES:
        raise Issue27PositiveIonWallError(f"unsupported A3 case mode {mode!r}")

    frozen = _validated_parameters(parameters)
    text, predecessor = build_r4_qf1_input(base_text)
    if predecessor["audit"]["status"] != "PASS":
        raise Issue27PositiveIonWallError("R4-QF1 predecessor audit is not PASS")

    flux = _flux_contract(parameters)
    wall_list = "'" + " ".join(PLASMA_WALLS) + "'"
    for path in (f"FVBCs/{BC_O2P}", f"FVBCs/{BC_OP}", f"FVBCs/{BC_O}"):
        mb.require_absent(text, path)
    mb.require_absent(text, f"Postprocessors/{AREA_PP}")

    o2p_on = mode == "o2p_only"
    op_on = mode == "op_only"
    values = {
        "O2p": -flux["J_O2p_out_kg_m2_s"] if o2p_on else 0.0,
        "Op": -flux["J_Op_out_kg_m2_s"] if op_on else 0.0,
        # Op -> O returns neutral O into the plasma, so physical J_O,out < 0.
        # A1 froze FVNeumannBC.value = -J_out; therefore the return value is positive.
        "O": -flux["J_O_return_for_Op_out_kg_m2_s"] if op_on else 0.0,
    }
    variables = {"O2p": "w_O2p", "Op": "w_Op", "O": "w_O"}
    names = {"O2p": BC_O2P, "Op": BC_OP, "O": BC_O}
    for species in ("O2p", "Op", "O"):
        text = mb.insert_child_block(
            text,
            "FVBCs",
            f"""  [{names[species]}]
    type = FVNeumannBC
    variable = {variables[species]}
    boundary = {wall_list}
    value = {values[species]:.17g}
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
        "mass_O2",
        "mass_O2p",
        "mass_O",
        "mass_Op",
        "w_O2_min",
        "w_O2p_min",
        "w_O_min",
        "w_Op_min",
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
        "experiment": "A3_R4_QF1_POSITIVE_ION_WALL_NEUTRALIZATION",
        "mode": mode,
        "predecessor": predecessor,
        "validated_parameters": frozen,
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "physical_flux_contract": flux,
        "moose_bc_values": values,
        "sign_contract": "physical outward positive -> FVNeumannBC value = -physical outward flux",
        "charge_contract": (
            "removing one singly positive ion from plasma changes volume charge by -e; "
            "SEE=0 and electron wall compensation are intentionally disabled"
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
    input_text, meta = _build_a3_case_input(base, parameters=parameters, mode=mode)
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
        "mass_O2",
        "mass_O2p",
        "mass_O",
        "mass_Op",
        "w_O2_min",
        "w_O2p_min",
        "w_O_min",
        "w_Op_min",
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


def _case_evidence(
    case: Mapping[str, Any],
    control: Mapping[str, Any],
    *,
    mode: str,
    flux: Mapping[str, float],
    area: float,
    dt: float,
) -> dict[str, Any]:
    def delta(key: str) -> float:
        return float(case[key]) - float(control[key])

    if mode == "o2p_only":
        expected_species = {
            "delta_mass_O2p_kg": -flux["J_O2p_out_kg_m2_s"] * area * dt,
            "delta_mass_O2_kg": +flux["J_O2p_out_kg_m2_s"] * area * dt,
        }
        expected_charge = flux["O2p_plasma_charge_rate_density_C_m2_s"] * area * dt
        measured_species = {
            "delta_mass_O2p_kg": delta("mass_O2p"),
            "delta_mass_O2_kg": delta("mass_O2"),
        }
    elif mode == "op_only":
        expected_species = {
            "delta_mass_Op_kg": -flux["J_Op_out_kg_m2_s"] * area * dt,
            "delta_mass_O_kg": -flux["J_O_return_for_Op_out_kg_m2_s"] * area * dt,
        }
        expected_charge = flux["Op_plasma_charge_rate_density_C_m2_s"] * area * dt
        measured_species = {
            "delta_mass_Op_kg": delta("mass_Op"),
            "delta_mass_O_kg": delta("mass_O"),
        }
    else:
        raise Issue27PositiveIonWallError(f"unsupported A3 evidence mode {mode!r}")

    measured_charge = delta("r31_charge_integral")
    gauss_defect = float(case["r31_gauss_flux_charge"]) - float(case["r31_charge_integral"])
    charge_scale = max(abs(expected_charge), 1.0e-300)
    transfer_scale = max(max(abs(value) for value in expected_species.values()), 1.0e-300)

    return {
        "mode": mode,
        "expected": {**expected_species, "delta_charge_C": expected_charge, "charge_sign": "negative"},
        "measured_delta_vs_control": {
            **measured_species,
            "delta_mass_total_kg": delta("mass_total"),
            "delta_charge_C": measured_charge,
            "delta_electron_inventory": delta("n_e_inventory"),
        },
        "species_relative_defects": {
            key: _rel_defect(measured_species[key], expected_species[key])
            for key in expected_species
        },
        "total_mass_relative_to_transfer": abs(delta("mass_total")) / transfer_scale,
        "charge_relative_defect": _rel_defect(measured_charge, expected_charge),
        "negative_volume_charge_shift": measured_charge < 0.0,
        "electron_inventory_relative_to_charge_scale": (
            abs(delta("n_e_inventory") * ELEMENTARY_CHARGE_C) / charge_scale
        ),
        "gauss_defect_C": gauss_defect,
        "nonnegative_state": all(
            float(case[key]) >= -1.0e-12
            for key in ("w_O2_min", "w_O2p_min", "w_O_min", "w_Op_min", "n_e_min")
        ),
    }


def _differential_evidence(
    states: Mapping[str, Mapping[str, Any]],
    *,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    if any(states[name].get("status") != "MEASURED" for name in CASE_MODES):
        return {"status": "MISSING", "error": "one or more A3 states are not measured"}

    frozen = _validated_parameters(parameters)
    flux = _flux_contract(parameters)
    control = states["control"]

    times = [float(states[name]["time"]) for name in CASE_MODES]
    if times[0] <= 0.0 or any(
        not math.isclose(times[0], value, rel_tol=0.0, abs_tol=1.0e-18)
        for value in times[1:]
    ):
        return {"status": "INVALID", "error": f"inconsistent final times: {times}"}
    dt = times[0]

    areas = [float(states[name][AREA_PP]) for name in CASE_MODES]
    if min(areas) <= 0.0 or any(
        not math.isclose(areas[0], value, rel_tol=1.0e-12, abs_tol=0.0)
        for value in areas[1:]
    ):
        return {"status": "INVALID", "error": f"inconsistent wall areas: {areas}"}
    area = areas[0]

    cases = {
        mode: _case_evidence(
            states[mode],
            control,
            mode=mode,
            flux=flux,
            area=area,
            dt=dt,
        )
        for mode in ("o2p_only", "op_only")
    }
    return {
        "status": "MEASURED",
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "final_time_s": dt,
        "combined_wall_area_m2": area,
        "parameters": frozen,
        "flux_contract": flux,
        "cases": cases,
        "all_negative_charge_shifts": all(
            cases[mode]["negative_volume_charge_shift"]
            for mode in ("o2p_only", "op_only")
        ),
        "all_nonnegative_states": all(
            cases[mode]["nonnegative_state"] for mode in ("o2p_only", "op_only")
        ),
        "scientific_acceptance": "UNSET_EVIDENCE_ONLY",
        "interpretation_contract": (
            "A3 isolates O2p -> constrained O2 and Op -> O with SEE=0. "
            "Each positive-ion loss must produce a negative plasma-volume charge shift. "
            "Electron wall compensation and finite SEE remain deferred."
        ),
    }


def run_positive_ion_wall_control(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue27PositiveIonWallError("timeout must be positive")

    exe = resolve_executable(qpx)
    validate_executable(exe)
    frozen = _validated_parameters(parameters)
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue27_a3_r4_qf1_positive_ion_neutralization_{stamp}",
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
        "experiment": "A3_positive_ion_wall_neutralization",
        "scientific_scope": (
            "prescribed O2+ -> constrained O2 and O+ -> O neutralization on all six "
            "plasma-facing walls; SEE=0 and electron wall compensation OFF"
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
        p2 = q0_run._p2(exe, cases_root / mode, logs / f"a3_{mode}_p2.log", timeout)
        summary["p2"][mode] = p2
        if p2["returncode"] != 0:
            summary["status"] = f"A3_P2_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A3_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 2

    states: dict[str, Mapping[str, Any]] = {}
    for mode in CASE_MODES:
        case_dir = cases_root / mode
        runtime = q0_run._runtime(exe, case_dir, logs / f"a3_{mode}_runtime.log", timeout)
        state = _read_final_state(case_dir / "input_out.csv")
        summary["cases"][mode] = {"runtime": runtime, "state": state}
        if runtime["returncode"] != 0:
            summary["status"] = f"A3_RUNTIME_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A3_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1
        states[mode] = state

    evidence = _differential_evidence(states, parameters=parameters)
    summary["differential"] = evidence
    summary["status"] = (
        "A3_POSITIVE_ION_CHARGE_SHIFT_EVIDENCE_READY_NOT_ACCEPTED"
        if evidence.get("status") == "MEASURED"
        else "A3_EVIDENCE_MISSING"
    )
    write_json_bundle(root, {"summary": ("summary.json", summary)})

    print(f"ISSUE27_A3_STATUS: {summary['status']}")
    if evidence.get("status") == "MEASURED":
        print(f"WALL_COUNT: {len(PLASMA_WALLS)}")
        print(f"COMBINED_WALL_AREA_M2: {evidence['combined_wall_area_m2']}")
        for mode in ("o2p_only", "op_only"):
            case = evidence["cases"][mode]
            print(f"{mode.upper()}_EXPECTED_DELTA_Q_C: {case['expected']['delta_charge_C']}")
            print(
                f"{mode.upper()}_MEASURED_DELTA_Q_C: "
                f"{case['measured_delta_vs_control']['delta_charge_C']}"
            )
            print(
                f"{mode.upper()}_CHARGE_RELATIVE_DEFECT: "
                f"{case['charge_relative_defect']}"
            )
            print(
                f"{mode.upper()}_NEGATIVE_VOLUME_CHARGE_SHIFT: "
                f"{case['negative_volume_charge_shift']}"
            )
            print(f"{mode.upper()}_GAUSS_DEFECT_C: {case['gauss_defect_C']}")
    print(f"EVIDENCE_DIR: {root}")
    return 0 if evidence.get("status") == "MEASURED" else 1


__all__ = [
    "Issue27PositiveIonWallError",
    "_build_a3_case_input",
    "_differential_evidence",
    "_flux_contract",
    "_validated_parameters",
    "run_positive_ion_wall_control",
]
