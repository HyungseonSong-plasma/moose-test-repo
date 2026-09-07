#!/usr/bin/env python3
"""Run Issue #26 E1 zero-source normalized electron-energy discriminator."""
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
    ENERGY_REFERENCE_EV,
    MEAN_EN_AVG_PP,
    MEAN_EN_MAX_PP,
    MEAN_EN_MIN_PP,
    build_issue26_e1_input,
)

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"
CASE_INITIALS = {
    "reference": 1.0,
    "half_energy": 0.5,
}


class Issue26E1RuntimeError(RuntimeError):
    pass


def _stage_case(
    target: Path,
    *,
    initial_energy_hat: float,
) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    input_text, meta = build_issue26_e1_input(
        base,
        initial_energy_hat=initial_energy_hat,
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
        expected["n0"] = float(meta["electron_reference_density_m3"])
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


def _required_columns() -> tuple[str, ...]:
    return (
        "time",
        ENERGY_INVENTORY_PP,
        ENERGY_NORM_AVG_PP,
        ENERGY_NORM_MIN_PP,
        ENERGY_NORM_MAX_PP,
        MEAN_EN_AVG_PP,
        MEAN_EN_MIN_PP,
        MEAN_EN_MAX_PP,
        "n_e_inventory",
        "n_e_min",
        "n_e_max",
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
            return {
                "status": "MISSING",
                "error": f"{label} missing CSV columns: {missing}",
            }
    try:
        initial = {name: float(rows[0][name]) for name in required}
        final = {name: float(rows[-1][name]) for name in required}
    except (TypeError, ValueError) as exc:
        return {"status": "INVALID", "error": str(exc)}
    if not all(math.isfinite(v) for v in (*initial.values(), *final.values())):
        return {"status": "INVALID", "error": "non-finite E1 state"}
    return {"status": "MEASURED", "initial": initial, "final": final}


def _rel_defect(measured: float, expected: float) -> float:
    return abs(measured - expected) / max(abs(expected), 1.0e-300)


def _case_evidence(
    state: Mapping[str, Any],
    *,
    target_energy_hat: float,
) -> dict[str, Any]:
    if state.get("status") != "MEASURED":
        return {"status": "MISSING", "error": "case state not measured"}
    initial = state["initial"]
    final = state["final"]
    initial_inventory = float(initial[ENERGY_INVENTORY_PP])
    final_inventory = float(final[ENERGY_INVENTORY_PP])
    final_avg = float(final[ENERGY_NORM_AVG_PP])
    final_min = float(final[ENERGY_NORM_MIN_PP])
    final_max = float(final[ENERGY_NORM_MAX_PP])
    return {
        "status": "MEASURED",
        "initial_energy_inventory_J": initial_inventory,
        "final_energy_inventory_J": final_inventory,
        "energy_inventory_relative_defect": _rel_defect(
            final_inventory,
            initial_inventory,
        ),
        "target_normalized_energy": target_energy_hat,
        "final_normalized_energy_avg": final_avg,
        "final_normalized_energy_min": final_min,
        "final_normalized_energy_max": final_max,
        "normalized_energy_avg_abs_error": abs(final_avg - target_energy_hat),
        "normalized_energy_peak_abs_error": max(
            abs(final_min - target_energy_hat),
            abs(final_max - target_energy_hat),
        ),
        "final_mean_energy_avg_eV": float(final[MEAN_EN_AVG_PP]),
        "final_mean_energy_min_eV": float(final[MEAN_EN_MIN_PP]),
        "final_mean_energy_max_eV": float(final[MEAN_EN_MAX_PP]),
        "final_n_e_inventory": float(final["n_e_inventory"]),
        "final_n_e_min_m3": float(final["n_e_min"]),
        "final_n_e_max_m3": float(final["n_e_max"]),
        "final_volume_charge_C": float(final["r31_charge_integral"]),
        "nonnegative_energy_state": final_min >= -1.0e-12,
        "positive_mean_energy": float(final[MEAN_EN_MIN_PP]) > 0.0,
    }


def _cross_case_evidence(cases: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if any(cases[name].get("status") != "MEASURED" for name in CASE_INITIALS):
        return {"status": "MISSING", "error": "one or more E1 cases not measured"}
    ref = cases["reference"]
    half = cases["half_energy"]
    ref_mean = float(ref["final_mean_energy_avg_eV"])
    half_mean = float(half["final_mean_energy_avg_eV"])
    ratio = half_mean / max(abs(ref_mean), 1.0e-300)
    ne_ref = float(ref["final_n_e_inventory"])
    ne_half = float(half["final_n_e_inventory"])
    q_ref = float(ref["final_volume_charge_C"])
    q_half = float(half["final_volume_charge_C"])
    return {
        "status": "MEASURED",
        "expected_mean_energy_ratio": 0.5,
        "measured_mean_energy_ratio": ratio,
        "mean_energy_ratio_abs_error": abs(ratio - 0.5),
        "electron_inventory_cross_case_relative_difference": (
            abs(ne_ref - ne_half) / max(abs(ne_ref), abs(ne_half), 1.0e-300)
        ),
        "volume_charge_cross_case_abs_difference_C": abs(q_ref - q_half),
        "interpretation": (
            "E1 energy state is passive by construction: solved energy does not drive "
            "electron transport lookup until E6, so the two cases must leave the accepted "
            "R4 particle/charge subsystem unchanged while preserving a 2:1 energy-state ratio."
        ),
    }


def run_e1_zero_source(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue26E1RuntimeError("timeout must be positive")
    if str(parameters.get("energy_model", "")) != "normalized_zero_source":
        raise Issue26E1RuntimeError(
            "E1 requires parameters.energy_model='normalized_zero_source'"
        )
    exe = resolve_executable(qpx)
    validate_executable(exe)

    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue26_e1_zero_source_{stamp}",
    )
    cases_root = root / "cases"
    logs = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    staged: dict[str, Any] = {}
    for mode, initial in CASE_INITIALS.items():
        staged[mode] = _stage_case(
            cases_root / mode,
            initial_energy_hat=initial,
        )

    summary: dict[str, Any] = {
        "issue": 26,
        "experiment": "E1_zero_source_normalized_electron_energy",
        "scientific_scope": (
            "Solved normalized electron-energy state with conservative transient only; "
            "energy transport, Joule source, wall-energy flux, SEE-energy source, solved-"
            "energy transport lookup coupling, and volumetric reaction energy sources OFF."
        ),
        "repository_head": issue91_run._repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": issue91_run._sha256(exe),
        "parameters": dict(parameters),
        "energy_reference_eV": ENERGY_REFERENCE_EV,
        "staged": staged,
        "p2": {},
        "cases": {},
        "evidence": {},
        "cross_case": {},
        "status": "NOT_RUN",
    }

    for mode in CASE_INITIALS:
        p2 = q0_run._p2(
            exe,
            cases_root / mode,
            logs / f"e1_{mode}_p2.log",
            timeout,
        )
        summary["p2"][mode] = p2
        if p2["returncode"] != 0:
            summary["status"] = f"E1_P2_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE26_E1_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 2

    for mode, initial in CASE_INITIALS.items():
        case_dir = cases_root / mode
        runtime = q0_run._runtime(
            exe,
            case_dir,
            logs / f"e1_{mode}_runtime.log",
            timeout,
        )
        state = _read_state(case_dir / "input_out.csv")
        evidence = _case_evidence(state, target_energy_hat=initial)
        summary["cases"][mode] = {"runtime": runtime, "state": state}
        summary["evidence"][mode] = evidence
        if runtime["returncode"] != 0:
            summary["status"] = f"E1_RUNTIME_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE26_E1_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1

    summary["cross_case"] = _cross_case_evidence(summary["evidence"])
    measured = all(
        summary["evidence"][mode].get("status") == "MEASURED"
        for mode in CASE_INITIALS
    ) and summary["cross_case"].get("status") == "MEASURED"
    summary["status"] = (
        "E1_ZERO_SOURCE_ENERGY_EVIDENCE_READY_NOT_ACCEPTED"
        if measured
        else "E1_EVIDENCE_MISSING"
    )
    summary["scientific_acceptance"] = "UNSET_EVIDENCE_ONLY"
    summary["acceptance_contract"] = (
        "Both positive uniform normalized energy states must remain conservative under "
        "the isolated FVTimeKernel, stay nonnegative, preserve their 2:1 solved mean-"
        "energy ratio, and leave the accepted R4 electron-particle/charge subsystem "
        "cross-case invariant. E1 does not validate energy transport or sources."
    )
    write_json_bundle(root, {"summary": ("summary.json", summary)})

    print(f"ISSUE26_E1_STATUS: {summary['status']}")
    if measured:
        for mode in CASE_INITIALS:
            item = summary["evidence"][mode]
            print(
                f"{mode.upper()}_ENERGY_INVENTORY_DEFECT: "
                f"{item['energy_inventory_relative_defect']}"
            )
            print(
                f"{mode.upper()}_ENERGY_PEAK_ERROR: "
                f"{item['normalized_energy_peak_abs_error']}"
            )
        print(
            "E1_MEAN_ENERGY_RATIO_ERROR: "
            f"{summary['cross_case']['mean_energy_ratio_abs_error']}"
        )
        print(
            "E1_ELECTRON_CROSS_CASE_DEFECT: "
            f"{summary['cross_case']['electron_inventory_cross_case_relative_difference']}"
        )
    print(f"EVIDENCE_DIR: {root}")
    return 0 if measured else 1


__all__ = [
    "CASE_INITIALS",
    "Issue26E1RuntimeError",
    "run_e1_zero_source",
]
