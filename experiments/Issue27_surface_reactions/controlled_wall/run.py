#!/usr/bin/env python3
"""Run Issue #27 A1 on the accepted R4-QF1 real-qvt baseline.

A1 is a bounded three-case differential discriminator:
  control : zero prescribed O wall flux
  plus    : +|J| FVNeumannBC value
  minus   : -|J| FVNeumannBC value

All three cases preserve the accepted R4-QF1 heavy/electron/Poisson feedback
construction.  Only the neutral-O wall flux on ``plasma_wafer`` changes.  The
control subtraction removes ordinary R4 transport/outlet evolution from the
wall-flux attribution.
"""
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

M_O_KG_PER_MOL = 0.016
DEFAULT_EVENT_FLUX_MOL_M2_S = 0.1
A1_WALL_BOUNDARY = "plasma_wafer"
A1_BC_NAME = "issue27_a1_O_wall_flux"
A1_WALL_AREA_PP = "issue27_a1_wall_area"
CASE_SIGNS: tuple[tuple[str, int], ...] = (
    ("control", 0),
    ("plus", 1),
    ("minus", -1),
)


class Issue27A1Error(RuntimeError):
    pass


def _float_parameter(parameters: Mapping[str, Any], name: str, default: float) -> float:
    raw = parameters.get(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise Issue27A1Error(f"parameters.{name} must be numeric") from exc
    if not math.isfinite(value):
        raise Issue27A1Error(f"parameters.{name} must be finite")
    return value


def _validated_parameters(parameters: Mapping[str, Any]) -> dict[str, float | str]:
    reaction_id = str(parameters.get("reaction_id", "O_to_half_O2"))
    if reaction_id != "O_to_half_O2":
        raise Issue27A1Error(
            "A1 currently accepts only reaction_id='O_to_half_O2'; "
            "extend the protocol only after A1 freezes the wall-flux sign contract"
        )
    event_flux = _float_parameter(
        parameters, "event_flux_mol_m2_s", DEFAULT_EVENT_FLUX_MOL_M2_S
    )
    if event_flux <= 0.0:
        raise Issue27A1Error("event_flux_mol_m2_s must be positive")

    wall = str(parameters.get("wall_boundary", A1_WALL_BOUNDARY))
    if wall != A1_WALL_BOUNDARY:
        raise Issue27A1Error(
            f"A1 wall_boundary is frozen to {A1_WALL_BOUNDARY!r}, got {wall!r}"
        )

    return {
        "reaction_id": reaction_id,
        "event_flux_mol_m2_s": event_flux,
        "wall_boundary": wall,
        "O_mass_flux_magnitude_kg_m2_s": event_flux * M_O_KG_PER_MOL,
        "experiment_flux_convention": "outward-from-plasma positive",
        "fvneumann_sign_mapping": "UNRESOLVED_UNTIL_PLUS_MINUS_RUNTIME",
    }


def _build_case_input(
    base_text: str,
    *,
    parameters: Mapping[str, Any],
    fvbc_sign: int,
) -> tuple[str, dict[str, Any]]:
    if fvbc_sign not in (-1, 0, 1):
        raise Issue27A1Error(f"fvbc_sign must be -1, 0, or 1, got {fvbc_sign}")

    frozen = _validated_parameters(parameters)
    text, predecessor = build_r4_qf1_input(base_text)
    if predecessor["audit"]["status"] != "PASS":
        raise Issue27A1Error("R4-QF1 predecessor audit is not PASS")

    for path in (
        f"FVBCs/{A1_BC_NAME}",
        f"Postprocessors/{A1_WALL_AREA_PP}",
    ):
        mb.require_absent(text, path)

    signed_value = fvbc_sign * float(frozen["O_mass_flux_magnitude_kg_m2_s"])
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{A1_BC_NAME}]
    type = FVNeumannBC
    variable = w_O
    boundary = {A1_WALL_BOUNDARY}
    value = {signed_value:.17g}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{A1_WALL_AREA_PP}]
    type = AreaPostprocessor
    boundary = {A1_WALL_BOUNDARY}
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )

    # Differential comparison requires the inventory/charge observables at the
    # same final R4 timestep in every case. Preserve all accepted physics and
    # only make their execution timing explicit.
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
        "experiment": "A1_R4_QF1_O_TO_HALF_O2_PRESCRIBED_WALL_FLUX",
        "predecessor": predecessor,
        "wall_boundary": A1_WALL_BOUNDARY,
        "fvbc": {
            "name": A1_BC_NAME,
            "type": "FVNeumannBC",
            "variable": "w_O",
            "value_kg_m2_s": signed_value,
            "sign_multiplier": fvbc_sign,
        },
        "surface_reaction": {
            "reaction": "O -> 0.5 O2",
            "event_flux_mol_m2_s": float(frozen["event_flux_mol_m2_s"]),
            "O_mass_flux_magnitude_kg_m2_s": float(
                frozen["O_mass_flux_magnitude_kg_m2_s"]
            ),
            "constrained_product": "O2",
        },
        "frozen_phase": {
            "R4_QF1_preserved": True,
            "volumetric_reactions": False,
            "secondary_emission": False,
            "surface_accumulated_charge": False,
        },
    }


def _stage_case(
    target: Path,
    *,
    parameters: Mapping[str, Any],
    fvbc_sign: int,
) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    input_text, meta = _build_case_input(
        base,
        parameters=parameters,
        fvbc_sign=fvbc_sign,
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


def _read_final_state(csv_path: Path) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        return {"status": "MISSING", "error": "need INITIAL and TIMESTEP_END rows"}

    required = (
        "time",
        A1_WALL_AREA_PP,
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


def _differential_evidence(
    case_states: Mapping[str, Mapping[str, Any]],
    *,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    frozen = _validated_parameters(parameters)
    if any(case_states[name].get("status") != "MEASURED" for name, _ in CASE_SIGNS):
        return {"status": "MISSING", "error": "one or more case states are not measured"}

    control = case_states["control"]
    plus = case_states["plus"]
    minus = case_states["minus"]

    dt_plus = float(plus["time"])
    dt_minus = float(minus["time"])
    dt_control = float(control["time"])
    if not (
        dt_plus > 0.0
        and math.isclose(dt_plus, dt_minus, rel_tol=0.0, abs_tol=1.0e-18)
        and math.isclose(dt_plus, dt_control, rel_tol=0.0, abs_tol=1.0e-18)
    ):
        return {
            "status": "INVALID",
            "error": (
                f"inconsistent final times: control={dt_control}, "
                f"plus={dt_plus}, minus={dt_minus}"
            ),
        }

    area_values = {
        name: float(case_states[name][A1_WALL_AREA_PP])
        for name, _ in CASE_SIGNS
    }
    area = area_values["control"]
    if area <= 0.0:
        return {"status": "INVALID", "error": f"non-positive wall area {area}"}

    flux = float(frozen["O_mass_flux_magnitude_kg_m2_s"])
    expected = flux * area * dt_control
    scale = max(abs(expected), 1.0e-300)

    def response(name: str) -> dict[str, float]:
        state = case_states[name]
        delta_o = float(state["mass_O"]) - float(control["mass_O"])
        delta_o2 = float(state["mass_O2"]) - float(control["mass_O2"])
        delta_total = float(state["mass_total"]) - float(control["mass_total"])
        delta_charge = float(state["r31_charge_integral"]) - float(
            control["r31_charge_integral"]
        )
        return {
            "delta_O_mass_vs_control_kg": delta_o,
            "delta_O2_mass_vs_control_kg": delta_o2,
            "delta_total_mass_vs_control_kg": delta_total,
            "delta_volume_charge_vs_control_C": delta_charge,
            "absolute_O_response_over_expected": abs(delta_o) / scale,
            "O_magnitude_relative_defect": abs(abs(delta_o) - expected) / scale,
            "O_O2_stoich_relative_defect": abs(delta_o + delta_o2) / scale,
            "total_mass_relative_to_surface_transfer": abs(delta_total) / scale,
        }

    plus_r = response("plus")
    minus_r = response("minus")
    delta_plus = plus_r["delta_O_mass_vs_control_kg"]
    delta_minus = minus_r["delta_O_mass_vs_control_kg"]

    if delta_plus < 0.0 < delta_minus:
        outward_loss_sign: int | None = 1
    elif delta_minus < 0.0 < delta_plus:
        outward_loss_sign = -1
    else:
        outward_loss_sign = None

    return {
        "status": "MEASURED",
        "wall_boundary": A1_WALL_BOUNDARY,
        "wall_area_by_case_m2": area_values,
        "final_time_s": dt_control,
        "imposed_O_mass_flux_magnitude_kg_m2_s": flux,
        "expected_single_case_transfer_magnitude_kg": expected,
        "control_final": dict(control),
        "plus": plus_r,
        "minus": minus_r,
        "plus_minus_antisymmetry_relative_defect": abs(delta_plus + delta_minus) / scale,
        "fvneumann_sign_for_outward_O_loss": outward_loss_sign,
        "experiment_outward_positive_mapping_resolved": outward_loss_sign is not None,
        "nonnegative_mass_fractions": all(
            float(case_states[name]["w_O_min"]) >= -1.0e-12
            and float(case_states[name]["w_O2_min"]) >= -1.0e-12
            for name, _ in CASE_SIGNS
        ),
        "charge_note": (
            "O -> 0.5 O2 is neutral; differential volume charge should remain near "
            "the control response. No charged-wall acceptance is inferred from A1."
        ),
        "acceptance": "MEASUREMENT_ONLY_PENDING_SCIENTIFIC_ADJUDICATION",
    }


def run_controlled_wall(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue27A1Error("timeout must be positive")
    frozen = _validated_parameters(parameters)
    exe = resolve_executable(qpx)
    validate_executable(exe)

    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue27_a1_r4_qf1_o_recombination_{stamp}",
    )
    cases_root = root / "cases"
    logs = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "issue": 27,
        "experiment": "A1_R4_QF1_O_recombination_prescribed_flux_differential",
        "scientific_scope": (
            "accepted R4-QF1 + neutral O prescribed wall flux on plasma_wafer; "
            "control/+/- differential sign and N-1 bookkeeping discriminator"
        ),
        "repository_head": issue91_run._repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": issue91_run._sha256(exe),
        "parameters": frozen,
        "cases": {},
        "differential": {},
        "status": "NOT_RUN",
    }

    # Stage and P2 all cases before spending runtime budget.
    for case_name, sign in CASE_SIGNS:
        case_dir = cases_root / case_name
        staged = _stage_case(
            case_dir,
            parameters=parameters,
            fvbc_sign=sign,
        )
        summary["cases"][case_name] = {
            "sign": sign,
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
            summary["status"] = f"A1_R4_P2_FAIL_{case_name.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A1_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 2

    for case_name, _ in CASE_SIGNS:
        case_dir = cases_root / case_name
        runtime = q0_run._runtime(
            exe,
            case_dir,
            logs / f"{case_name}_runtime.log",
            timeout,
        )
        summary["cases"][case_name]["runtime"] = runtime
        if runtime["returncode"] != 0:
            summary["status"] = f"A1_R4_RUNTIME_FAIL_{case_name.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A1_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1

        state = _read_final_state(case_dir / "input_out.csv")
        summary["cases"][case_name]["state"] = state
        if state.get("status") != "MEASURED":
            summary["status"] = f"A1_R4_EVIDENCE_MISSING_{case_name.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A1_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1

    states = {
        name: summary["cases"][name]["state"]
        for name, _ in CASE_SIGNS
    }
    differential = _differential_evidence(states, parameters=parameters)
    summary["differential"] = differential
    if differential.get("status") != "MEASURED":
        summary["status"] = "A1_R4_DIFFERENTIAL_EVIDENCE_MISSING"
    else:
        summary["status"] = "A1_R4_EVIDENCE_READY_NOT_ACCEPTED"

    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"ISSUE27_A1_STATUS: {summary['status']}")
    if differential.get("status") == "MEASURED":
        print(
            "FVNEUMANN_SIGN_FOR_OUTWARD_O_LOSS: "
            f"{differential['fvneumann_sign_for_outward_O_loss']}"
        )
        print(
            "PLUS_DELTA_O_KG: "
            f"{differential['plus']['delta_O_mass_vs_control_kg']:.17g}"
        )
        print(
            "MINUS_DELTA_O_KG: "
            f"{differential['minus']['delta_O_mass_vs_control_kg']:.17g}"
        )
        print(
            "PLUS_MAGNITUDE_DEFECT: "
            f"{differential['plus']['O_magnitude_relative_defect']:.17g}"
        )
        print(
            "MINUS_MAGNITUDE_DEFECT: "
            f"{differential['minus']['O_magnitude_relative_defect']:.17g}"
        )
        print(
            "ANTISYMMETRY_DEFECT: "
            f"{differential['plus_minus_antisymmetry_relative_defect']:.17g}"
        )
    print(f"EVIDENCE_DIR: {root}")
    return 0 if summary["status"] == "A1_R4_EVIDENCE_READY_NOT_ACCEPTED" else 1


__all__ = [
    "Issue27A1Error",
    "run_controlled_wall",
    "_validated_parameters",
    "_build_case_input",
    "_differential_evidence",
]
