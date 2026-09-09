#!/usr/bin/env python3
"""Run Issue #27 A1b state-dependent O sticking on accepted R4-QF1."""
from __future__ import annotations

import csv
import json
import math
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

GAS_CONSTANT_J_PER_MOL_K = 8.31446
M_O_KG_PER_MOL = 0.016
DEFAULT_STICKING_COEFFICIENT = 0.2
A1B_WALL_BOUNDARY = "plasma_wafer"
A1B_FLUX_MATERIAL = "issue27_a1b_O_sticking_flux"
A1B_FLUX_FUNCTOR = "issue27_a1b_O_wall_flux_outward"
A1B_BC_NAME = "issue27_a1b_O_sticking_wall_flux"
A1B_WALL_AREA_PP = "issue27_a1b_wall_area"
A1B_WALL_RATE_PP = "issue27_a1b_O_wall_mass_rate_outward"
A1B_CASES: tuple[tuple[str, float], ...] = (
    ("control", 0.0),
    ("sticking", -1.0),
)


class Issue27A1bError(RuntimeError):
    pass


def _float_parameter(parameters: Mapping[str, Any], name: str, default: float) -> float:
    raw = parameters.get(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise Issue27A1bError(f"parameters.{name} must be numeric") from exc
    if not math.isfinite(value):
        raise Issue27A1bError(f"parameters.{name} must be finite")
    return value


def _validated_sticking_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    reaction_id = str(parameters.get("reaction_id", "O_to_half_O2"))
    if reaction_id != "O_to_half_O2":
        raise Issue27A1bError(
            "A1b currently accepts only reaction_id='O_to_half_O2'"
        )

    wall_model = str(parameters.get("wall_model", ""))
    if wall_model != "sticking":
        raise Issue27A1bError("A1b requires parameters.wall_model='sticking'")

    wall = str(parameters.get("wall_boundary", A1B_WALL_BOUNDARY))
    if wall != A1B_WALL_BOUNDARY:
        raise Issue27A1bError(
            f"A1b wall_boundary is frozen to {A1B_WALL_BOUNDARY!r}, got {wall!r}"
        )

    gamma = _float_parameter(
        parameters, "sticking_coefficient", DEFAULT_STICKING_COEFFICIENT
    )
    if not 0.0 < gamma <= 1.0:
        raise Issue27A1bError("sticking_coefficient must lie in (0, 1]")

    motz_wise = parameters.get("motz_wise_correction", False)
    if not isinstance(motz_wise, bool):
        raise Issue27A1bError("motz_wise_correction must be boolean")
    if motz_wise:
        raise Issue27A1bError(
            "A1b is frozen to Motz-Wise OFF; a corrected variant requires a separate discriminator"
        )

    gas_temperature_functor = str(parameters.get("gas_temperature_functor", "T_g"))
    if gas_temperature_functor != "T_g":
        raise Issue27A1bError("A1b gas_temperature_functor is frozen to 'T_g'")

    kinetic_gamma = gamma
    thermal_speed_expression = (
        f"sqrt(8.0*{GAS_CONSTANT_J_PER_MOL_K:.17g}*tg/"
        f"(3.14159265358979323846*{M_O_KG_PER_MOL:.17g}))"
    )
    outward_mass_flux_expression = (
        f"{kinetic_gamma:.17g}*0.25*{thermal_speed_expression}*rho*wo"
    )
    return {
        "reaction_id": reaction_id,
        "wall_model": wall_model,
        "wall_boundary": wall,
        "sticking_coefficient": gamma,
        "motz_wise_correction": False,
        "gas_temperature_functor": gas_temperature_functor,
        "molar_mass_O_kg_per_mol": M_O_KG_PER_MOL,
        "gas_constant_J_per_mol_K": GAS_CONSTANT_J_PER_MOL_K,
        "rate_model": (
            "Motz-Wise OFF: k_s = gamma*(1/4)*sqrt(8*R*T_g/(pi*M_O)); "
            "J_O,out = k_s*rho*w_O"
        ),
        "outward_mass_flux_expression": outward_mass_flux_expression,
        "moose_flux_factor": -1.0,
        "moose_sign_basis": (
            "A1 runtime froze outward-from-plasma O loss as FVNeumannBC value = -J_out"
        ),
    }


def _build_sticking_case_input(
    base_text: str,
    *,
    parameters: Mapping[str, Any],
    bc_factor: float,
) -> tuple[str, dict[str, Any]]:
    if bc_factor not in (0.0, -1.0):
        raise Issue27A1bError(f"bc_factor must be 0 or -1, got {bc_factor}")

    frozen = _validated_sticking_parameters(parameters)
    text, predecessor = build_r4_qf1_input(base_text)
    if predecessor["audit"]["status"] != "PASS":
        raise Issue27A1bError("R4-QF1 predecessor audit is not PASS")

    for path in (
        f"FunctorMaterials/{A1B_FLUX_MATERIAL}",
        f"FVBCs/{A1B_BC_NAME}",
        f"Postprocessors/{A1B_WALL_AREA_PP}",
        f"Postprocessors/{A1B_WALL_RATE_PP}",
    ):
        mb.require_absent(text, path)

    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{A1B_FLUX_MATERIAL}]
    type = ADParsedFunctorMaterial
    property_name = {A1B_FLUX_FUNCTOR}
    functor_names = 'rho_mat w_O T_g'
    functor_symbols = 'rho wo tg'
    expression = '{frozen["outward_mass_flux_expression"]}'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{A1B_BC_NAME}]
    type = FVFunctorNeumannBC
    variable = w_O
    boundary = {A1B_WALL_BOUNDARY}
    functor = {A1B_FLUX_FUNCTOR}
    factor = {bc_factor:.17g}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{A1B_WALL_AREA_PP}]
    type = AreaPostprocessor
    boundary = {A1B_WALL_BOUNDARY}
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{A1B_WALL_RATE_PP}]
    type = ADSideIntegralFunctorPostprocessor
    boundary = {A1B_WALL_BOUNDARY}
    functor = {A1B_FLUX_FUNCTOR}
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )

    for pp in (
        "mass_O",
        "mass_O2",
        "mass_total",
        "w_O_min",
        "w_O2_min",
        "r31_charge_integral",
    ):
        text = mp.upsert_parameter(
            text,
            f"Postprocessors/{pp}",
            "execute_on",
            "'INITIAL TIMESTEP_END'",
        )

    return text, {
        "issue": 27,
        "experiment": "A1B_R4_QF1_O_TO_HALF_O2_STICKING",
        "predecessor": predecessor,
        "wall_boundary": A1B_WALL_BOUNDARY,
        "surface_reaction": {
            "reaction": "O -> 0.5 O2",
            **frozen,
        },
        "fvbc": {
            "name": A1B_BC_NAME,
            "type": "FVFunctorNeumannBC",
            "variable": "w_O",
            "functor": A1B_FLUX_FUNCTOR,
            "factor": bc_factor,
            "outward_positive_functor": True,
        },
        "frozen_phase": {
            "R4_QF1_preserved": True,
            "volumetric_reactions": False,
            "secondary_emission": False,
            "surface_accumulated_charge": False,
        },
    }


def _stage_sticking_case(
    target: Path,
    *,
    parameters: Mapping[str, Any],
    bc_factor: float,
) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    input_text, meta = _build_sticking_case_input(
        base,
        parameters=parameters,
        bc_factor=bc_factor,
    )
    staging = stage_case(
        SOURCE,
        target,
        input_text=input_text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=(
            "input_out*",
            "*.log",
            "*.e",
            "*.exo",
            "prepare_evidence.json",
        ),
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
        expected_path.write_text(
            json.dumps(expected, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

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


def _read_sticking_final_state(csv_path: Path) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        return {"status": "MISSING", "error": "need INITIAL and TIMESTEP_END rows"}

    required = (
        "time",
        A1B_WALL_AREA_PP,
        A1B_WALL_RATE_PP,
        "mass_O",
        "mass_O2",
        "mass_total",
        "w_O_min",
        "w_O2_min",
        "r31_charge_integral",
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


def _sticking_differential_evidence(
    case_states: Mapping[str, Mapping[str, Any]],
    *,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    frozen = _validated_sticking_parameters(parameters)
    if any(
        case_states[name].get("status") != "MEASURED"
        for name, _ in A1B_CASES
    ):
        return {"status": "MISSING", "error": "one or more A1b states are not measured"}

    control = case_states["control"]
    sticking = case_states["sticking"]
    time_control = float(control["time"])
    time_sticking = float(sticking["time"])
    if not (
        time_control > 0.0
        and math.isclose(time_control, time_sticking, rel_tol=0.0, abs_tol=1.0e-18)
    ):
        return {
            "status": "INVALID",
            "error": (
                f"inconsistent final times: control={time_control}, "
                f"sticking={time_sticking}"
            ),
        }

    area_control = float(control[A1B_WALL_AREA_PP])
    area_sticking = float(sticking[A1B_WALL_AREA_PP])
    wall_rate = float(sticking[A1B_WALL_RATE_PP])
    if area_control <= 0.0 or area_sticking <= 0.0 or wall_rate <= 0.0:
        return {
            "status": "INVALID",
            "error": (
                f"invalid A1b area/rate: control_area={area_control}, "
                f"sticking_area={area_sticking}, wall_rate={wall_rate}"
            ),
        }

    expected_transfer = wall_rate * time_sticking
    scale = max(abs(expected_transfer), 1.0e-300)
    delta_o = float(sticking["mass_O"]) - float(control["mass_O"])
    delta_o2 = float(sticking["mass_O2"]) - float(control["mass_O2"])
    delta_total = float(sticking["mass_total"]) - float(control["mass_total"])
    delta_charge = float(sticking["r31_charge_integral"]) - float(
        control["r31_charge_integral"]
    )

    return {
        "status": "MEASURED",
        "wall_boundary": A1B_WALL_BOUNDARY,
        "sticking_coefficient": float(frozen["sticking_coefficient"]),
        "motz_wise_correction": False,
        "final_time_s": time_sticking,
        "wall_area_control_m2": area_control,
        "wall_area_sticking_m2": area_sticking,
        "control_hypothetical_wall_mass_rate_kg_s": float(control[A1B_WALL_RATE_PP]),
        "sticking_applied_wall_mass_rate_kg_s": wall_rate,
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
        "rate_model": frozen["rate_model"],
        "charge_note": (
            "A1b reaction is neutral; differential charge is diagnostic only and "
            "does not establish charged-wall acceptance."
        ),
        "acceptance": "MEASUREMENT_ONLY_PENDING_SCIENTIFIC_ADJUDICATION",
    }


def run_sticking_wall(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue27A1bError("timeout must be positive")
    frozen = _validated_sticking_parameters(parameters)
    exe = resolve_executable(qpx)
    validate_executable(exe)

    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue27_a1b_r4_qf1_o_sticking_{stamp}",
    )
    cases_root = root / "cases"
    logs = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "issue": 27,
        "experiment": "A1B_R4_QF1_O_recombination_sticking_differential",
        "scientific_scope": (
            "accepted R4-QF1 + state-dependent neutral O sticking wall flux on "
            "plasma_wafer; control/sticking differential with Motz-Wise OFF"
        ),
        "repository_head": issue91_run._repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": issue91_run._sha256(exe),
        "parameters": frozen,
        "cases": {},
        "differential": {},
        "status": "NOT_RUN",
    }

    for case_name, factor in A1B_CASES:
        case_dir = cases_root / case_name
        staged = _stage_sticking_case(
            case_dir,
            parameters=parameters,
            bc_factor=factor,
        )
        summary["cases"][case_name] = {
            "factor": factor,
            "staged": staged,
            "p2": {},
            "runtime": {},
            "state": {},
        }
        p2 = q0_run._p2(
            exe,
            case_dir,
            logs / f"{case_name}_p2.log",
            timeout,
        )
        summary["cases"][case_name]["p2"] = p2
        if p2["returncode"] != 0:
            summary["status"] = f"A1B_R4_P2_FAIL_{case_name.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A1B_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 2

    for case_name, _ in A1B_CASES:
        case_dir = cases_root / case_name
        runtime = q0_run._runtime(
            exe,
            case_dir,
            logs / f"{case_name}_runtime.log",
            timeout,
        )
        summary["cases"][case_name]["runtime"] = runtime
        if runtime["returncode"] != 0:
            summary["status"] = f"A1B_R4_RUNTIME_FAIL_{case_name.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A1B_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1

        state = _read_sticking_final_state(case_dir / "input_out.csv")
        summary["cases"][case_name]["state"] = state
        if state.get("status") != "MEASURED":
            summary["status"] = f"A1B_R4_EVIDENCE_MISSING_{case_name.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A1B_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1

    states = {
        name: summary["cases"][name]["state"]
        for name, _ in A1B_CASES
    }
    differential = _sticking_differential_evidence(states, parameters=parameters)
    summary["differential"] = differential
    if differential.get("status") != "MEASURED":
        summary["status"] = "A1B_R4_DIFFERENTIAL_EVIDENCE_MISSING"
    else:
        summary["status"] = "A1B_R4_EVIDENCE_READY_NOT_ACCEPTED"

    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"ISSUE27_A1B_STATUS: {summary['status']}")
    if differential.get("status") == "MEASURED":
        print(f"STICKING_COEFFICIENT: {differential['sticking_coefficient']:.17g}")
        print("MOTZ_WISE_CORRECTION: false")
        print(
            "FINAL_WALL_MASS_RATE_KG_S: "
            f"{differential['sticking_applied_wall_mass_rate_kg_s']:.17g}"
        )
        print(
            "EXPECTED_TRANSFER_KG: "
            f"{differential['implicit_euler_expected_O_transfer_kg']:.17g}"
        )
        print(
            "DELTA_O_KG: "
            f"{differential['delta_O_mass_vs_control_kg']:.17g}"
        )
        print(
            "MAGNITUDE_DEFECT: "
            f"{differential['O_magnitude_relative_defect']:.17g}"
        )
        print(
            "O_O2_STOICH_DEFECT: "
            f"{differential['O_O2_stoich_relative_defect']:.17g}"
        )
        print(
            "DELTA_CHARGE_C: "
            f"{differential['delta_volume_charge_vs_control_C']:.17g}"
        )
    print(f"EVIDENCE_DIR: {root}")
    return 0 if summary["status"] == "A1B_R4_EVIDENCE_READY_NOT_ACCEPTED" else 1


__all__ = [
    "A1B_BC_NAME",
    "A1B_FLUX_FUNCTOR",
    "A1B_FLUX_MATERIAL",
    "A1B_WALL_AREA_PP",
    "A1B_WALL_RATE_PP",
    "Issue27A1bError",
    "_build_sticking_case_input",
    "_sticking_differential_evidence",
    "_validated_sticking_parameters",
    "run_sticking_wall",
]
