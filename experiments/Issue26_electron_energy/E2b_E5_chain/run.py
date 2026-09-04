#!/usr/bin/env python3
"""Run the Issue #26 E2b-E5 integrated electron-energy promotion chain."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping

from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue91_real_qvt_r3 import run as issue91_run
from qpx_harness.evidence import create_collision_safe_directory, utc_timestamp, write_json_bundle
from qpx_harness.execution.cases import stage_case
from qpx_harness.execution.runtime import resolve_executable, validate_executable
from recipes.issue26_e1 import (
    ENERGY_INVENTORY_PP,
    ENERGY_NORM_MAX_PP,
    ENERGY_NORM_MIN_PP,
)
from recipes.issue26_energy_chain import (
    A8_SEE_ENERGY_PP,
    E2B_DT_S,
    E2B_FIELD_V_M,
    E2B_LEFT_PP,
    E2B_MOBILITY_M2_V_S,
    E2B_RIGHT_PP,
    E3_DT_S,
    E3_FIELD_V_M,
    E3_JOULE_POWER_PP,
    E3_MOBILITY_M2_V_S,
    ENERGY_WALL_THERMAL_POWER_PP,
    SEE_ENERGY_COUPLED_POWER_PP,
    build_e2b_drift_input,
    build_e3_joule_input,
    build_e4_e5_wall_input,
)

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"

E2B_CASES = {
    "e2b_zero_field": 0.0,
    "e2b_plus_field": E2B_FIELD_V_M,
    "e2b_minus_field": -E2B_FIELD_V_M,
}
E3_CASES = {
    "e3_joule_off": 0.0,
    "e3_joule_on": E3_FIELD_V_M,
}
WALL_CASES = {
    "e4_thermal_energy": (False, False),
    "e5_see_energy_off": (True, False),
    "e5_see_energy_on": (True, True),
}


class Issue26EnergyChainRuntimeError(RuntimeError):
    pass


def _validate_parameters(parameters: Mapping[str, Any]) -> None:
    if str(parameters.get("energy_chain", "")) != "e2b_to_e5_controlled":
        raise Issue26EnergyChainRuntimeError(
            "energy-chain experiment requires parameters.energy_chain='e2b_to_e5_controlled'"
        )
    expected = {
        "e2b_field_V_m": E2B_FIELD_V_M,
        "e2b_mobility_m2_V_s": E2B_MOBILITY_M2_V_S,
        "e3_field_V_m": E3_FIELD_V_M,
        "e3_mobility_m2_V_s": E3_MOBILITY_M2_V_S,
        "secondary_electron_mean_energy_eV": 4.0,
    }
    for name, value in expected.items():
        actual = float(parameters.get(name, value))
        if not math.isclose(actual, value, rel_tol=0.0, abs_tol=0.0):
            raise Issue26EnergyChainRuntimeError(
                f"parameters.{name} is frozen to {value}, got {actual}"
            )


def _n_ref(meta: Mapping[str, Any]) -> float:
    if "electron_reference_density_m3" in meta:
        return float(meta["electron_reference_density_m3"])
    predecessor = meta.get("predecessor")
    if isinstance(predecessor, Mapping) and "electron_reference_density_m3" in predecessor:
        return float(predecessor["electron_reference_density_m3"])
    raise Issue26EnergyChainRuntimeError("construction metadata has no electron reference density")


def _stage(
    target: Path,
    builder: Callable[[str], tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    input_text, meta = builder(base)
    staging = stage_case(
        SOURCE,
        target,
        input_text=input_text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    expected_path = target / "expected.json"
    if expected_path.is_file():
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        expected["field_strength"] = 0.0
        expected["n0"] = _n_ref(meta)
        expected_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
    (target / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"source": str(SOURCE.resolve()), "staging": staging, "construction": meta}


def _read_state(csv_path: Path, required: tuple[str, ...]) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        return {"status": "MISSING", "error": "need INITIAL and TIMESTEP_END rows"}
    for label, row in (("initial", rows[0]), ("final", rows[-1])):
        missing = [name for name in required if name not in row]
        if missing:
            return {"status": "MISSING", "error": f"{label} missing columns: {missing}"}
    try:
        initial = {name: float(rows[0][name]) for name in required}
        final = {name: float(rows[-1][name]) for name in required}
    except (TypeError, ValueError) as exc:
        return {"status": "INVALID", "error": str(exc)}
    if not all(math.isfinite(value) for value in (*initial.values(), *final.values())):
        return {"status": "INVALID", "error": "non-finite state"}
    return {"status": "MEASURED", "initial": initial, "final": final}


def _rel_defect(measured: float, expected: float) -> float:
    return abs(measured - expected) / max(abs(expected), 1.0e-30)


def _inventory_defect(state: Mapping[str, Any]) -> float:
    initial = float(state["initial"][ENERGY_INVENTORY_PP])
    final = float(state["final"][ENERGY_INVENTORY_PP])
    return abs(final - initial) / max(abs(initial), 1.0e-30)


def _e2b_evidence(states: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if any(states[name].get("status") != "MEASURED" for name in E2B_CASES):
        return {"status": "MISSING"}
    cases: dict[str, Any] = {}
    for name in E2B_CASES:
        state = states[name]
        cases[name] = {
            "energy_inventory_relative_defect": _inventory_defect(state),
            "initial_left": float(state["initial"][E2B_LEFT_PP]),
            "final_left": float(state["final"][E2B_LEFT_PP]),
            "initial_right": float(state["initial"][E2B_RIGHT_PP]),
            "final_right": float(state["final"][E2B_RIGHT_PP]),
            "final_energy_min": float(state["final"][ENERGY_NORM_MIN_PP]),
            "final_energy_max": float(state["final"][ENERGY_NORM_MAX_PP]),
        }
    zero = cases["e2b_zero_field"]
    plus = cases["e2b_plus_field"]
    minus = cases["e2b_minus_field"]
    initial_probe_spread = max(
        abs(cases[a][probe] - cases[b][probe])
        for a in cases
        for b in cases
        for probe in ("initial_left", "initial_right")
    )
    return {
        "status": "MEASURED",
        "cases": cases,
        "initial_probe_cross_case_max_abs_difference": initial_probe_spread,
        "plus_field_left_delta_vs_zero": plus["final_left"] - zero["final_left"],
        "plus_field_right_delta_vs_zero": plus["final_right"] - zero["final_right"],
        "minus_field_left_delta_vs_zero": minus["final_left"] - zero["final_left"],
        "minus_field_right_delta_vs_zero": minus["final_right"] - zero["final_right"],
        "expected_direction": {
            "plus_field": "left probe increases and right probe decreases",
            "minus_field": "left probe decreases and right probe increases",
        },
    }


def _e3_evidence(states: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if any(states[name].get("status") != "MEASURED" for name in E3_CASES):
        return {"status": "MISSING"}
    out: dict[str, Any] = {"status": "MEASURED", "cases": {}}
    for name in E3_CASES:
        state = states[name]
        initial_energy = float(state["initial"][ENERGY_INVENTORY_PP])
        final_energy = float(state["final"][ENERGY_INVENTORY_PP])
        final_power = float(state["final"][E3_JOULE_POWER_PP])
        expected_delta = final_power * E3_DT_S
        measured_delta = final_energy - initial_energy
        out["cases"][name] = {
            "initial_energy_J": initial_energy,
            "final_energy_J": final_energy,
            "final_applied_joule_power_W": final_power,
            "measured_energy_delta_J": measured_delta,
            "expected_backward_euler_energy_delta_J": expected_delta,
            "energy_budget_relative_defect": (
                _rel_defect(measured_delta, expected_delta)
                if abs(expected_delta) > 0.0
                else abs(measured_delta)
            ),
        }
    return out


def _wall_case_evidence(
    state: Mapping[str, Any],
    *,
    dt_s: float,
) -> dict[str, Any]:
    if state.get("status") != "MEASURED":
        return {"status": "MISSING"}
    initial_energy = float(state["initial"][ENERGY_INVENTORY_PP])
    final_energy = float(state["final"][ENERGY_INVENTORY_PP])
    thermal_power = abs(float(state["final"][ENERGY_WALL_THERMAL_POWER_PP]))
    see_ledger_power = abs(float(state["final"][A8_SEE_ENERGY_PP]))
    see_coupled_power = abs(float(state["final"][SEE_ENERGY_COUPLED_POWER_PP]))
    expected_delta = (-thermal_power + see_coupled_power) * dt_s
    measured_delta = final_energy - initial_energy
    return {
        "status": "MEASURED",
        "initial_energy_J": initial_energy,
        "final_energy_J": final_energy,
        "measured_energy_delta_J": measured_delta,
        "final_thermal_energy_loss_power_W": thermal_power,
        "final_a8_see_4eV_ledger_power_W": see_ledger_power,
        "final_coupled_see_energy_power_W": see_coupled_power,
        "expected_backward_euler_energy_delta_J": expected_delta,
        "energy_budget_relative_defect": _rel_defect(measured_delta, expected_delta),
        "see_energy_power_coupling_relative_defect": (
            _rel_defect(see_coupled_power, see_ledger_power)
            if see_ledger_power > 0.0
            else abs(see_coupled_power)
        ),
        "final_energy_min": float(state["final"][ENERGY_NORM_MIN_PP]),
        "final_electron_inventory": float(state["final"]["n_e_inventory"]),
        "final_volume_charge_C": float(state["final"]["r31_charge_integral"]),
    }


def _wall_evidence(states: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if any(states[name].get("status") != "MEASURED" for name in WALL_CASES):
        return {"status": "MISSING"}
    cases = {
        name: _wall_case_evidence(states[name], dt_s=1.0e-10)
        for name in WALL_CASES
    }
    off = cases["e5_see_energy_off"]
    on = cases["e5_see_energy_on"]
    return {
        "status": "MEASURED",
        "cases": cases,
        "e5_particle_subsystem_cross_case": {
            "electron_inventory_relative_difference": abs(
                on["final_electron_inventory"] - off["final_electron_inventory"]
            ) / max(
                abs(on["final_electron_inventory"]),
                abs(off["final_electron_inventory"]),
                1.0e-30,
            ),
            "volume_charge_abs_difference_C": abs(
                on["final_volume_charge_C"] - off["final_volume_charge_C"]
            ),
            "interpretation": (
                "SEE energy coupling must remain passive with respect to the particle/Poisson "
                "subsystem until solved mean energy is connected back in a later stage."
            ),
        },
    }


def run_energy_chain(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue26EnergyChainRuntimeError("timeout must be positive")
    _validate_parameters(parameters)
    exe = resolve_executable(qpx)
    validate_executable(exe)

    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue26_energy_chain_{stamp}",
    )
    cases_root = root / "cases"
    logs = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    staged: dict[str, Any] = {}
    for name, field in E2B_CASES.items():
        staged[name] = _stage(
            cases_root / name,
            lambda base, field=field: build_e2b_drift_input(
                base,
                field_v_m=field,
                mobility_m2_v_s=E2B_MOBILITY_M2_V_S,
            ),
        )
    for name, field in E3_CASES.items():
        staged[name] = _stage(
            cases_root / name,
            lambda base, field=field: build_e3_joule_input(
                base,
                field_v_m=field,
                mobility_m2_v_s=E3_MOBILITY_M2_V_S,
            ),
        )
    for name, (see_particle_on, see_energy_on) in WALL_CASES.items():
        staged[name] = _stage(
            cases_root / name,
            lambda base, spo=see_particle_on, seo=see_energy_on: build_e4_e5_wall_input(
                base,
                see_particle_on=spo,
                see_energy_on=seo,
            ),
        )

    summary: dict[str, Any] = {
        "issue": 26,
        "experiment": "E2B_E5_INTEGRATED_ELECTRON_ENERGY_CHAIN",
        "repository_head": issue91_run._repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": issue91_run._sha256(exe),
        "parameters": dict(parameters),
        "scientific_scope": (
            "One-shot controlled promotion chain: energy drift sign, drift-only Joule heating, "
            "COMSOL thermal energy wall loss, and A8 4 eV SEE energy coupling. Production "
            "mu_epsilon/D_epsilon provenance, solved-field Joule coupling, solved-energy "
            "transport lookup feedback, volumetric reaction energy losses, and physical ICP "
            "plasma-potential acceptance remain outside this chain."
        ),
        "predecessor_assumption": "E1 and E2a accepted from prior user-local evidence",
        "staged": staged,
        "p2": {},
        "runtime": {},
        "states": {},
        "evidence": {},
        "status": "NOT_RUN",
        "scientific_acceptance": "UNSET_EVIDENCE_ONLY",
    }

    all_case_names = tuple(E2B_CASES) + tuple(E3_CASES) + tuple(WALL_CASES)
    for name in all_case_names:
        p2 = q0_run._p2(
            exe,
            cases_root / name,
            logs / f"{name}_p2.log",
            timeout,
        )
        summary["p2"][name] = p2

    required_by_case: dict[str, tuple[str, ...]] = {}
    e2b_required = (
        "time",
        ENERGY_INVENTORY_PP,
        ENERGY_NORM_MIN_PP,
        ENERGY_NORM_MAX_PP,
        E2B_LEFT_PP,
        E2B_RIGHT_PP,
        "n_e_inventory",
        "r31_charge_integral",
    )
    e3_required = (
        "time",
        ENERGY_INVENTORY_PP,
        E3_JOULE_POWER_PP,
        "n_e_inventory",
        "r31_charge_integral",
    )
    wall_required = (
        "time",
        ENERGY_INVENTORY_PP,
        ENERGY_NORM_MIN_PP,
        ENERGY_WALL_THERMAL_POWER_PP,
        A8_SEE_ENERGY_PP,
        SEE_ENERGY_COUPLED_POWER_PP,
        "n_e_inventory",
        "r31_charge_integral",
    )
    for name in E2B_CASES:
        required_by_case[name] = e2b_required
    for name in E3_CASES:
        required_by_case[name] = e3_required
    for name in WALL_CASES:
        required_by_case[name] = wall_required

    for name in all_case_names:
        if summary["p2"][name]["returncode"] != 0:
            summary["runtime"][name] = {
                "returncode": None,
                "status": "SKIPPED_P2_FAILURE",
            }
            summary["states"][name] = {"status": "MISSING", "error": "P2 failure"}
            continue
        runtime = q0_run._runtime(
            exe,
            cases_root / name,
            logs / f"{name}_runtime.log",
            timeout,
        )
        summary["runtime"][name] = runtime
        summary["states"][name] = _read_state(
            cases_root / name / "input_out.csv",
            required_by_case[name],
        )

    summary["evidence"]["E2b"] = _e2b_evidence(summary["states"])
    summary["evidence"]["E3"] = _e3_evidence(summary["states"])
    summary["evidence"]["E4_E5"] = _wall_evidence(summary["states"])

    complete = (
        all(summary["p2"][name]["returncode"] == 0 for name in all_case_names)
        and all(
            summary["runtime"][name].get("returncode") == 0
            for name in all_case_names
        )
        and all(
            summary["evidence"][stage].get("status") == "MEASURED"
            for stage in ("E2b", "E3", "E4_E5")
        )
    )
    summary["status"] = (
        "ENERGY_CHAIN_EVIDENCE_READY_NOT_ACCEPTED"
        if complete
        else "ENERGY_CHAIN_INCOMPLETE"
    )
    summary["acceptance_contract"] = {
        "E2b": (
            "closed-boundary energy drift conserves inventory and reverses the left/right "
            "probe response when E_x is reversed"
        ),
        "E3": (
            "controlled drift-only Joule source increases energy by final applied power * dt "
            "under backward Euler; zero-field control remains unchanged"
        ),
        "E4": (
            "thermal energy wall loss closes ΔE = -P_thermal(final)*dt on the six solid walls"
        ),
        "E5": (
            "with A8 particle SEE fixed, 4 eV energy coupling closes "
            "ΔE = (-P_thermal + P_SEE,coupled)*dt and the coupled power matches the A8 ledger"
        ),
    }

    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"ISSUE26_ENERGY_CHAIN_STATUS: {summary['status']}")
    if summary["evidence"]["E2b"].get("status") == "MEASURED":
        e2b = summary["evidence"]["E2b"]
        print(f"E2B_PLUS_LEFT_DELTA: {e2b['plus_field_left_delta_vs_zero']}")
        print(f"E2B_PLUS_RIGHT_DELTA: {e2b['plus_field_right_delta_vs_zero']}")
        print(f"E2B_MINUS_LEFT_DELTA: {e2b['minus_field_left_delta_vs_zero']}")
        print(f"E2B_MINUS_RIGHT_DELTA: {e2b['minus_field_right_delta_vs_zero']}")
    if summary["evidence"]["E3"].get("status") == "MEASURED":
        print(
            "E3_JOULE_ON_BUDGET_DEFECT: "
            f"{summary['evidence']['E3']['cases']['e3_joule_on']['energy_budget_relative_defect']}"
        )
    if summary["evidence"]["E4_E5"].get("status") == "MEASURED":
        wall = summary["evidence"]["E4_E5"]["cases"]
        print(
            "E4_THERMAL_BUDGET_DEFECT: "
            f"{wall['e4_thermal_energy']['energy_budget_relative_defect']}"
        )
        print(
            "E5_SEE_ENERGY_BUDGET_DEFECT: "
            f"{wall['e5_see_energy_on']['energy_budget_relative_defect']}"
        )
        print(
            "E5_SEE_POWER_COUPLING_DEFECT: "
            f"{wall['e5_see_energy_on']['see_energy_power_coupling_relative_defect']}"
        )
    print(f"EVIDENCE_DIR: {root}")
    return 0 if complete else 1


__all__ = ["Issue26EnergyChainRuntimeError", "run_energy_chain"]
