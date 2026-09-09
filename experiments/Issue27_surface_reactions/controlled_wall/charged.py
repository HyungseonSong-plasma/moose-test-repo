#!/usr/bin/env python3
"""Run Issue #27 prescribed charged-wall flux + electron charge-ledger control on R4-QF1."""
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue91_real_qvt_r3 import run as issue91_run
from physics_harness.evidence import create_collision_safe_directory, utc_timestamp, write_json_bundle
from physics_harness.execution.cases import stage_case
from physics_harness.execution.runtime import resolve_executable, validate_executable
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
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
CASE_MODES = ("control", "heavy_only", "charge_balanced")
AREA_PP = "issue27_charged_wall_area"
BC_NAMES = {
    "O2p": "issue27_O2p_wall_loss",
    "Om": "issue27_Om_wall_loss",
    "Op": "issue27_Op_wall_loss",
    "O": "issue27_O_wall_return",
    "electron": "issue27_electron_wall_absorption",
}


class Issue27ChargedWallError(RuntimeError):
    pass


def _top_level_float(text: str, name: str) -> float:
    matches = re.findall(rf"(?m)^\s*{re.escape(name)}\s*=\s*([^#\r\n]+)", text)
    if len(matches) != 1:
        raise Issue27ChargedWallError(f"cannot resolve unique top-level scalar {name}")
    value = float(matches[0].strip())
    if not math.isfinite(value):
        raise Issue27ChargedWallError(f"non-finite scalar {name}={value}")
    return value


def _float_parameter(parameters: Mapping[str, Any], name: str, default: float) -> float:
    raw = parameters.get(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise Issue27ChargedWallError(f"parameters.{name} must be numeric") from exc
    if not math.isfinite(value):
        raise Issue27ChargedWallError(f"parameters.{name} must be finite")
    return value


def _validated_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    wall_model = str(parameters.get("wall_model", ""))
    if wall_model != "charged_prescribed_ledger":
        raise Issue27ChargedWallError(
            "charged control requires wall_model='charged_prescribed_ledger'"
        )
    wall_scope = str(parameters.get("wall_scope", ""))
    if wall_scope != "all_plasma_walls":
        raise Issue27ChargedWallError("charged control requires wall_scope='all_plasma_walls'")
    see = _float_parameter(parameters, "secondary_emission_coefficient", 0.0)
    if see != 0.0:
        raise Issue27ChargedWallError("charged control is frozen to SEE=0")

    r_o2p = _float_parameter(parameters, "O2p_event_flux_mol_m2_s", 1.0e-4)
    r_op = _float_parameter(parameters, "Op_event_flux_mol_m2_s", 1.0e-4)
    r_om = _float_parameter(parameters, "Om_event_flux_mol_m2_s", 5.0e-5)
    if min(r_o2p, r_op, r_om) <= 0.0:
        raise Issue27ChargedWallError("all charged event fluxes must be positive")

    r_e = r_o2p + r_op - r_om
    if r_e <= 0.0:
        raise Issue27ChargedWallError(
            "electron absorption rate must be positive: require O2p + Op > Om"
        )

    return {
        "wall_model": wall_model,
        "wall_scope": wall_scope,
        "wall_boundaries": list(PLASMA_WALLS),
        "secondary_emission_coefficient": 0.0,
        "O2p_event_flux_mol_m2_s": r_o2p,
        "Op_event_flux_mol_m2_s": r_op,
        "Om_event_flux_mol_m2_s": r_om,
        "electron_absorption_molar_flux_mol_m2_s": r_e,
        "electron_absorption_particle_flux_m2_s": AVOGADRO * r_e,
        "charge_balance_contract": (
            "Gamma_e,abs = N_A*(R_O2p + R_Op - R_Om), SEE=0; "
            "heavy-only is a positive charge-shift control, balanced adds electron absorption"
        ),
        "surface_reactions": ["O2p -> O2", "Op -> O", "Om -> O"],
        "production_sheath_kinetics": False,
    }


def _flux_contract(parameters: Mapping[str, Any], n_ref_m3: float) -> dict[str, float]:
    frozen = _validated_parameters(parameters)
    r_o2p = float(frozen["O2p_event_flux_mol_m2_s"])
    r_op = float(frozen["Op_event_flux_mol_m2_s"])
    r_om = float(frozen["Om_event_flux_mol_m2_s"])
    r_e = float(frozen["electron_absorption_molar_flux_mol_m2_s"])
    return {
        "J_O2p_out_kg_m2_s": M_O2_KG_PER_MOL * r_o2p,
        "J_Op_out_kg_m2_s": M_O_KG_PER_MOL * r_op,
        "J_Om_out_kg_m2_s": M_O_KG_PER_MOL * r_om,
        "J_O_out_kg_m2_s": -M_O_KG_PER_MOL * (r_op + r_om),
        "electron_particle_flux_out_m2_s": AVOGADRO * r_e,
        "electron_normalized_flux_out_m_s": AVOGADRO * r_e / n_ref_m3,
        "net_heavy_charge_current_density_A_m2": FARADAY_C_PER_MOL * r_e,
    }


def _build_charged_case_input(
    base_text: str,
    *,
    parameters: Mapping[str, Any],
    mode: str,
) -> tuple[str, dict[str, Any]]:
    if mode not in CASE_MODES:
        raise Issue27ChargedWallError(f"unsupported charged case mode {mode!r}")
    frozen = _validated_parameters(parameters)
    text, predecessor = build_r4_qf1_input(base_text)
    if predecessor["audit"]["status"] != "PASS":
        raise Issue27ChargedWallError("R4-QF1 predecessor audit is not PASS")

    n_ref = _top_level_float(text, "n_e_value")
    flux = _flux_contract(parameters, n_ref)
    wall_list = "'" + " ".join(PLASMA_WALLS) + "'"

    for path in [f"FVBCs/{name}" for name in BC_NAMES.values()]:
        mb.require_absent(text, path)
    mb.require_absent(text, f"Postprocessors/{AREA_PP}")

    heavy_on = mode in ("heavy_only", "charge_balanced")
    electron_on = mode == "charge_balanced"
    values = {
        "O2p": -flux["J_O2p_out_kg_m2_s"] if heavy_on else 0.0,
        "Op": -flux["J_Op_out_kg_m2_s"] if heavy_on else 0.0,
        "Om": -flux["J_Om_out_kg_m2_s"] if heavy_on else 0.0,
        # Physical O flux is inward (negative outward) because Op/Om neutralize to O.
        # A1 froze MOOSE value = -J_out, therefore the O-return BC value is positive.
        "O": -flux["J_O_out_kg_m2_s"] if heavy_on else 0.0,
        # Electron solver unknown is n_hat = n_e/n_ref.  Its conservative physical
        # number flux is therefore Gamma_e/n_ref in the normalized equation.
        "electron": -flux["electron_normalized_flux_out_m_s"] if electron_on else 0.0,
    }
    variables = {"O2p": "w_O2p", "Op": "w_Op", "Om": "w_Om", "O": "w_O", "electron": "n_e"}
    for species in ("O2p", "Op", "Om", "O", "electron"):
        text = mb.insert_child_block(
            text,
            "FVBCs",
            f"""  [{BC_NAMES[species]}]
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
        "mass_Om",
        "mass_Op",
        "w_O2_min",
        "w_O2p_min",
        "w_O_min",
        "w_Om_min",
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
        "experiment": "A3E_R4_QF1_CHARGED_WALL_CHARGE_LEDGER",
        "mode": mode,
        "predecessor": predecessor,
        "validated_parameters": frozen,
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "electron_reference_density_m3": n_ref,
        "physical_flux_contract": flux,
        "moose_bc_values": values,
        "sign_contract": "physical outward positive -> FVNeumannBC value = -physical outward flux",
        "electron_normalization_contract": (
            "n_e solver unknown is n_hat; electron FVNeumann value is -Gamma_e,out/n_ref"
        ),
        "frozen_phase": {
            "R4_QF1_preserved": True,
            "volumetric_reactions": False,
            "secondary_emission": False,
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
    input_text, meta = _build_charged_case_input(base, parameters=parameters, mode=mode)
    staging = stage_case(
        SOURCE,
        target,
        input_text=input_text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    reference = float(meta["electron_reference_density_m3"])
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
        "mass_Om",
        "mass_Op",
        "w_O2_min",
        "w_O2p_min",
        "w_O_min",
        "w_Om_min",
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


def _differential_evidence(
    states: Mapping[str, Mapping[str, Any]],
    *,
    parameters: Mapping[str, Any],
    n_ref_m3: float,
) -> dict[str, Any]:
    if any(states[name].get("status") != "MEASURED" for name in CASE_MODES):
        return {"status": "MISSING", "error": "one or more charged-wall states are not measured"}
    frozen = _validated_parameters(parameters)
    flux = _flux_contract(parameters, n_ref_m3)
    control = states["control"]
    heavy = states["heavy_only"]
    balanced = states["charge_balanced"]

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

    expected = {
        "delta_mass_O2p_kg": -flux["J_O2p_out_kg_m2_s"] * area * dt,
        "delta_mass_Op_kg": -flux["J_Op_out_kg_m2_s"] * area * dt,
        "delta_mass_Om_kg": -flux["J_Om_out_kg_m2_s"] * area * dt,
        "delta_mass_O_kg": -flux["J_O_out_kg_m2_s"] * area * dt,
        "delta_mass_O2_kg": flux["J_O2p_out_kg_m2_s"] * area * dt,
        "electron_inventory_loss_balanced_vs_heavy": (
            flux["electron_particle_flux_out_m2_s"] * area * dt
        ),
        "heavy_only_delta_charge_C": (
            -flux["net_heavy_charge_current_density_A_m2"] * area * dt
        ),
        "balanced_delta_charge_C": 0.0,
    }

    def delta(case: Mapping[str, Any], ref: Mapping[str, Any], key: str) -> float:
        return float(case[key]) - float(ref[key])

    heavy_delta = {
        "mass_O2p": delta(heavy, control, "mass_O2p"),
        "mass_Op": delta(heavy, control, "mass_Op"),
        "mass_Om": delta(heavy, control, "mass_Om"),
        "mass_O": delta(heavy, control, "mass_O"),
        "mass_O2": delta(heavy, control, "mass_O2"),
        "mass_total": delta(heavy, control, "mass_total"),
        "charge_C": delta(heavy, control, "r31_charge_integral"),
    }
    balanced_delta = {
        "mass_O2p": delta(balanced, control, "mass_O2p"),
        "mass_Op": delta(balanced, control, "mass_Op"),
        "mass_Om": delta(balanced, control, "mass_Om"),
        "mass_O": delta(balanced, control, "mass_O"),
        "mass_O2": delta(balanced, control, "mass_O2"),
        "mass_total": delta(balanced, control, "mass_total"),
        "charge_C": delta(balanced, control, "r31_charge_integral"),
    }
    electron_loss = -delta(balanced, heavy, "n_e_inventory")
    gauss_balanced_defect = float(balanced["r31_gauss_flux_charge"]) - float(
        balanced["r31_charge_integral"]
    )

    species_defects = {
        "O2p": _rel_defect(heavy_delta["mass_O2p"], expected["delta_mass_O2p_kg"]),
        "Op": _rel_defect(heavy_delta["mass_Op"], expected["delta_mass_Op_kg"]),
        "Om": _rel_defect(heavy_delta["mass_Om"], expected["delta_mass_Om_kg"]),
        "O_return": _rel_defect(heavy_delta["mass_O"], expected["delta_mass_O_kg"]),
        "constrained_O2_return": _rel_defect(heavy_delta["mass_O2"], expected["delta_mass_O2_kg"]),
    }
    charge_scale = max(abs(expected["heavy_only_delta_charge_C"]), 1.0e-300)
    return {
        "status": "MEASURED",
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "final_time_s": dt,
        "combined_wall_area_m2": area,
        "parameters": frozen,
        "flux_contract": flux,
        "expected": expected,
        "heavy_only_delta_vs_control": heavy_delta,
        "charge_balanced_delta_vs_control": balanced_delta,
        "heavy_species_relative_defects": species_defects,
        "electron_inventory_loss_balanced_vs_heavy": electron_loss,
        "electron_inventory_relative_defect": _rel_defect(
            electron_loss,
            expected["electron_inventory_loss_balanced_vs_heavy"],
        ),
        "heavy_only_charge_relative_defect": _rel_defect(
            heavy_delta["charge_C"],
            expected["heavy_only_delta_charge_C"],
        ),
        "charge_restoration_ratio": abs(balanced_delta["charge_C"]) / charge_scale,
        "balanced_gauss_defect_C": gauss_balanced_defect,
        "balanced_total_mass_relative_to_heavy_transfer": abs(balanced_delta["mass_total"]) / max(
            abs(expected["delta_mass_O2p_kg"])
            + abs(expected["delta_mass_Op_kg"])
            + abs(expected["delta_mass_Om_kg"]),
            1.0e-300,
        ),
        "nonnegative_state": all(
            float(balanced[key]) >= -1.0e-12
            for key in ("w_O2_min", "w_O2p_min", "w_O_min", "w_Om_min", "w_Op_min", "n_e_min")
        ),
        "scientific_acceptance": "UNSET_EVIDENCE_ONLY",
        "interpretation_contract": (
            "heavy_only must show the prescribed net heavy charge shift; charge_balanced "
            "adds only the matched electron wall absorption and should restore DeltaQ toward control"
        ),
    }


def run_charged_wall_ledger(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue27ChargedWallError("timeout must be positive")
    exe = resolve_executable(qpx)
    validate_executable(exe)
    frozen = _validated_parameters(parameters)
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue27_a3e_r4_qf1_charged_wall_ledger_{stamp}",
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
    n_ref = float(staged["control"]["construction"]["electron_reference_density_m3"])

    summary: dict[str, Any] = {
        "issue": 27,
        "experiment": "A3e_charged_wall_charge_ledger",
        "scientific_scope": (
            "prescribed O2+/O+/O- wall neutralization with matched electron absorption; "
            "charge-ledger control only, not production sheath kinetics"
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
        p2 = q0_run._p2(exe, cases_root / mode, logs / f"a3e_{mode}_p2.log", timeout)
        summary["p2"][mode] = p2
        if p2["returncode"] != 0:
            summary["status"] = f"A3E_P2_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A3E_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 2

    states: dict[str, Mapping[str, Any]] = {}
    for mode in CASE_MODES:
        case_dir = cases_root / mode
        runtime = q0_run._runtime(exe, case_dir, logs / f"a3e_{mode}_runtime.log", timeout)
        state = _read_final_state(case_dir / "input_out.csv")
        summary["cases"][mode] = {"runtime": runtime, "state": state}
        if runtime["returncode"] != 0:
            summary["status"] = f"A3E_RUNTIME_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A3E_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1
        states[mode] = state

    evidence = _differential_evidence(states, parameters=parameters, n_ref_m3=n_ref)
    summary["differential"] = evidence
    summary["status"] = (
        "A3E_CHARGE_LEDGER_EVIDENCE_READY_NOT_ACCEPTED"
        if evidence.get("status") == "MEASURED"
        else "A3E_EVIDENCE_MISSING"
    )
    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"ISSUE27_A3E_STATUS: {summary['status']}")
    if evidence.get("status") == "MEASURED":
        print(f"WALL_COUNT: {len(PLASMA_WALLS)}")
        print(f"COMBINED_WALL_AREA_M2: {evidence['combined_wall_area_m2']}")
        print(f"HEAVY_ONLY_DELTA_Q_C: {evidence['heavy_only_delta_vs_control']['charge_C']}")
        print(f"BALANCED_DELTA_Q_C: {evidence['charge_balanced_delta_vs_control']['charge_C']}")
        print(f"CHARGE_RESTORATION_RATIO: {evidence['charge_restoration_ratio']}")
        print(f"ELECTRON_INVENTORY_DEFECT: {evidence['electron_inventory_relative_defect']}")
    print(f"EVIDENCE_DIR: {root}")
    return 0 if evidence.get("status") == "MEASURED" else 1


__all__ = [
    "PLASMA_WALLS",
    "Issue27ChargedWallError",
    "_build_charged_case_input",
    "_validated_parameters",
    "run_charged_wall_ledger",
]
