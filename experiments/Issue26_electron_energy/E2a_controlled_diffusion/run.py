#!/usr/bin/env python3
"""Run Issue #26 E2a controlled electron-energy diffusion discriminator."""
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
from experiments.historical_recipe_support.issue26_e1 import (
    ENERGY_INVENTORY_PP,
    ENERGY_NORM_AVG_PP,
    ENERGY_NORM_MAX_PP,
    ENERGY_NORM_MIN_PP,
)
from experiments.historical_recipe_support.issue26_e2a import E2A_DIFFUSIVITY_M2_S, build_issue26_e2a_input

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"
CASE_DIFFUSIVITIES = {
    "zero_diffusion": 0.0,
    "diffusion": E2A_DIFFUSIVITY_M2_S,
}


class Issue26E2ARuntimeError(RuntimeError):
    pass


def _stage_case(target: Path, *, diffusivity_m2_s: float) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    input_text, meta = build_issue26_e2a_input(
        base,
        diffusivity_m2_s=diffusivity_m2_s,
    )
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
        expected["n0"] = float(meta["predecessor"]["electron_reference_density_m3"])
        expected_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
    (target / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"source": str(SOURCE.resolve()), "staging": staging, "construction": meta}


def _required_columns() -> tuple[str, ...]:
    return (
        "time",
        ENERGY_INVENTORY_PP,
        ENERGY_NORM_AVG_PP,
        ENERGY_NORM_MIN_PP,
        ENERGY_NORM_MAX_PP,
        "n_e_inventory",
        "r31_charge_integral",
    )


def _read_state(csv_path: Path) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        return {"status": "MISSING", "error": "need INITIAL and TIMESTEP_END rows"}
    required = _required_columns()
    for label, row in (("initial", rows[0]), ("final", rows[-1])):
        missing = [name for name in required if name not in row]
        if missing:
            return {"status": "MISSING", "error": f"{label} missing CSV columns: {missing}"}
    try:
        initial = {name: float(rows[0][name]) for name in required}
        final = {name: float(rows[-1][name]) for name in required}
    except (TypeError, ValueError) as exc:
        return {"status": "INVALID", "error": str(exc)}
    if not all(math.isfinite(v) for v in (*initial.values(), *final.values())):
        return {"status": "INVALID", "error": "non-finite E2a state"}
    return {"status": "MEASURED", "initial": initial, "final": final}


def _rel_defect(measured: float, expected: float) -> float:
    return abs(measured - expected) / max(abs(expected), 1.0e-300)


def _case_evidence(state: Mapping[str, Any], *, diffusivity_m2_s: float) -> dict[str, Any]:
    if state.get("status") != "MEASURED":
        return {"status": "MISSING", "error": "case state not measured"}
    initial = state["initial"]
    final = state["final"]
    initial_min = float(initial[ENERGY_NORM_MIN_PP])
    initial_max = float(initial[ENERGY_NORM_MAX_PP])
    final_min = float(final[ENERGY_NORM_MIN_PP])
    final_max = float(final[ENERGY_NORM_MAX_PP])
    initial_range = initial_max - initial_min
    final_range = final_max - final_min
    return {
        "status": "MEASURED",
        "diffusivity_m2_s": diffusivity_m2_s,
        "initial_energy_inventory_J": float(initial[ENERGY_INVENTORY_PP]),
        "final_energy_inventory_J": float(final[ENERGY_INVENTORY_PP]),
        "energy_inventory_relative_defect": _rel_defect(
            float(final[ENERGY_INVENTORY_PP]),
            float(initial[ENERGY_INVENTORY_PP]),
        ),
        "initial_normalized_energy_avg": float(initial[ENERGY_NORM_AVG_PP]),
        "final_normalized_energy_avg": float(final[ENERGY_NORM_AVG_PP]),
        "initial_normalized_energy_min": initial_min,
        "initial_normalized_energy_max": initial_max,
        "final_normalized_energy_min": final_min,
        "final_normalized_energy_max": final_max,
        "initial_profile_range": initial_range,
        "final_profile_range": final_range,
        "profile_range_ratio": final_range / max(initial_range, 1.0e-300),
        "final_n_e_inventory": float(final["n_e_inventory"]),
        "final_volume_charge_C": float(final["r31_charge_integral"]),
        "nonnegative_energy_state": final_min >= -1.0e-12,
    }


def _cross_case_evidence(cases: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if any(cases[name].get("status") != "MEASURED" for name in CASE_DIFFUSIVITIES):
        return {"status": "MISSING", "error": "one or more E2a cases not measured"}
    control = cases["zero_diffusion"]
    diffusion = cases["diffusion"]
    initial_inventory_scale = max(
        abs(float(control["initial_energy_inventory_J"])),
        abs(float(diffusion["initial_energy_inventory_J"])),
        1.0e-300,
    )
    return {
        "status": "MEASURED",
        "initial_inventory_cross_case_relative_difference": abs(
            float(control["initial_energy_inventory_J"])
            - float(diffusion["initial_energy_inventory_J"])
        )
        / initial_inventory_scale,
        "initial_average_cross_case_abs_difference": abs(
            float(control["initial_normalized_energy_avg"])
            - float(diffusion["initial_normalized_energy_avg"])
        ),
        "initial_range_cross_case_abs_difference": abs(
            float(control["initial_profile_range"])
            - float(diffusion["initial_profile_range"])
        ),
        "zero_diffusion_profile_range_ratio": float(control["profile_range_ratio"]),
        "diffusion_profile_range_ratio": float(diffusion["profile_range_ratio"]),
        "diffusion_contract_observed": (
            float(diffusion["final_profile_range"])
            < float(diffusion["initial_profile_range"])
        ),
        "zero_diffusion_control_observed": math.isclose(
            float(control["final_profile_range"]),
            float(control["initial_profile_range"]),
            rel_tol=1.0e-10,
            abs_tol=1.0e-12,
        ),
        "interpretation": (
            "Both cases start from the same nonuniform normalized energy profile. "
            "The zero-diffusion control must preserve that profile while the prescribed "
            "positive-diffusion case contracts its range without changing total energy."
        ),
    }


def run_e2a_controlled_diffusion(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue26E2ARuntimeError("timeout must be positive")
    if str(parameters.get("energy_model", "")) != "controlled_diffusion":
        raise Issue26E2ARuntimeError(
            "E2a requires parameters.energy_model='controlled_diffusion'"
        )
    exe = resolve_executable(qpx)
    validate_executable(exe)

    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue26_e2a_controlled_diffusion_{stamp}",
    )
    cases_root = root / "cases"
    logs = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    staged: dict[str, Any] = {}
    for mode, diffusivity in CASE_DIFFUSIVITIES.items():
        staged[mode] = _stage_case(
            cases_root / mode,
            diffusivity_m2_s=diffusivity,
        )

    summary: dict[str, Any] = {
        "issue": 26,
        "experiment": "E2a_controlled_electron_energy_diffusion",
        "scientific_scope": (
            "Solved normalized electron-energy transient plus controlled FVDiffusion. "
            "Energy drift, Joule source, wall-energy flux, SEE-energy source, solved-energy "
            "transport lookup coupling, and volumetric reaction energy sources remain OFF."
        ),
        "repository_head": issue91_run._repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": issue91_run._sha256(exe),
        "parameters": dict(parameters),
        "case_diffusivities_m2_s": CASE_DIFFUSIVITIES,
        "staged": staged,
        "p2": {},
        "cases": {},
        "evidence": {},
        "cross_case": {},
        "status": "NOT_RUN",
    }

    for mode in CASE_DIFFUSIVITIES:
        p2 = q0_run._p2(
            exe,
            cases_root / mode,
            logs / f"e2a_{mode}_p2.log",
            timeout,
        )
        summary["p2"][mode] = p2
        if p2["returncode"] != 0:
            summary["status"] = f"E2A_P2_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE26_E2A_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 2

    for mode, diffusivity in CASE_DIFFUSIVITIES.items():
        case_dir = cases_root / mode
        runtime = q0_run._runtime(
            exe,
            case_dir,
            logs / f"e2a_{mode}_runtime.log",
            timeout,
        )
        state = _read_state(case_dir / "input_out.csv")
        evidence = _case_evidence(state, diffusivity_m2_s=diffusivity)
        summary["cases"][mode] = {"runtime": runtime, "state": state}
        summary["evidence"][mode] = evidence
        if runtime["returncode"] != 0:
            summary["status"] = f"E2A_RUNTIME_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE26_E2A_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1

    summary["cross_case"] = _cross_case_evidence(summary["evidence"])
    measured = all(
        summary["evidence"][mode].get("status") == "MEASURED"
        for mode in CASE_DIFFUSIVITIES
    ) and summary["cross_case"].get("status") == "MEASURED"
    summary["status"] = (
        "E2A_CONTROLLED_DIFFUSION_EVIDENCE_READY_NOT_ACCEPTED"
        if measured
        else "E2A_EVIDENCE_MISSING"
    )
    summary["scientific_acceptance"] = "UNSET_EVIDENCE_ONLY"
    summary["acceptance_contract"] = (
        "The common nonuniform energy profile must be preserved by the zero-diffusion "
        "control, smoothed by the positive prescribed diffusivity, remain nonnegative, "
        "and conserve total electron-energy inventory in both cases under natural zero "
        "energy-flux boundaries. E2a does not validate production energy coefficients."
    )
    write_json_bundle(root, {"summary": ("summary.json", summary)})

    print(f"ISSUE26_E2A_STATUS: {summary['status']}")
    if measured:
        for mode in CASE_DIFFUSIVITIES:
            item = summary["evidence"][mode]
            print(
                f"{mode.upper()}_ENERGY_INVENTORY_DEFECT: "
                f"{item['energy_inventory_relative_defect']}"
            )
            print(
                f"{mode.upper()}_PROFILE_RANGE_RATIO: "
                f"{item['profile_range_ratio']}"
            )
        print(
            "E2A_INITIAL_INVENTORY_CROSS_CASE_DEFECT: "
            f"{summary['cross_case']['initial_inventory_cross_case_relative_difference']}"
        )
    print(f"EVIDENCE_DIR: {root}")
    return 0 if measured else 1


__all__ = [
    "CASE_DIFFUSIVITIES",
    "Issue26E2ARuntimeError",
    "run_e2a_controlled_diffusion",
]
