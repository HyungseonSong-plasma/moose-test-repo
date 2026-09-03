#!/usr/bin/env python3
"""Run Issue #31 R4-QN0 quasi-neutral all-ground solved-Poisson discriminator."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue91_real_qvt_r3 import run as issue91_run
from qpx_harness.evidence import create_collision_safe_directory, utc_timestamp, write_json_bundle
from qpx_harness.execution.cases import stage_case
from qpx_harness.execution.runtime import resolve_executable, validate_executable
from recipes.issue31_r4_qn0 import build_r4_qn0_input

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"


def _stage(target: Path) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text()
    input_text, meta = build_r4_qn0_input(base)
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

    expected_path = target / "expected.json"
    expected = json.loads(expected_path.read_text())
    expected["field_strength"] = 0.0
    expected["n0"] = float(
        meta["quasi_neutral_reference"]["electron_reference_density_m3"]
    )
    expected_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")

    (target / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n"
    )
    return {
        "source": str(SOURCE.resolve()),
        "staging": staging,
        "construction": meta,
        "expected": expected,
    }


def _state_evidence(csv_path: Path) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"status": "MISSING", "error": "physical CSV has no rows"}
    row = rows[-1]
    required = (
        "time",
        "domain_volume",
        "n_e_avg",
        "n_e_min",
        "n_e_max",
        "r31_charge_integral",
        "r31_phi_min",
        "r31_phi_max",
    )
    missing = [name for name in required if name not in row]
    if missing:
        return {"status": "MISSING", "error": f"missing state columns: {missing}"}
    try:
        values = {name: float(row[name]) for name in required}
    except (TypeError, ValueError) as exc:
        return {"status": "INVALID", "error": str(exc)}

    volume = values["domain_volume"]
    if volume <= 0.0:
        return {"status": "INVALID", "error": f"non-positive domain volume {volume}"}
    q_volume = values["r31_charge_integral"]
    phi_min = values["r31_phi_min"]
    phi_max = values["r31_phi_max"]
    return {
        "status": "MEASURED",
        "time": values["time"],
        "domain_volume_m3": volume,
        "electron_density_avg_m3": values["n_e_avg"],
        "electron_density_min_m3": values["n_e_min"],
        "electron_density_max_m3": values["n_e_max"],
        "volume_charge_C": q_volume,
        "average_charge_density_C_per_m3": q_volume / volume,
        "phi_min_V": phi_min,
        "phi_max_V": phi_max,
        "phi_span_V": phi_max - phi_min,
        "phi_abs_max_V": max(abs(phi_min), abs(phi_max)),
        "acceptance": "UNSET_QN0_CONTROL_MEASUREMENT",
    }


def run(args: argparse.Namespace) -> int:
    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        args.results_root,
        f"issue31_r4_qn0_all_ground_{stamp}",
    )
    case_dir = root / "case"
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    staged = _stage(case_dir)
    reference = float(
        staged["construction"]["quasi_neutral_reference"][
            "electron_reference_density_m3"
        ]
    )
    summary: dict[str, Any] = {
        "issue": 31,
        "experiment": "r4-qn0-all-ground-quasi-neutral-volume-charge-poisson",
        "repository_head": issue91_run._repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": issue91_run._sha256(exe),
        "phase": {
            "volume_charge": True,
            "poisson": True,
            "quasi_neutral_initialization": True,
            "electrostatic_feedback": False,
            "surface_accumulated_charge": False,
            "all_ground_phi": True,
        },
        "electron_reference_density_m3": reference,
        "staged": staged,
        "p2": {},
        "runtime": {},
        "r3_invariants": {},
        "gauss_law": {},
        "state": {},
        "status": "NOT_RUN",
    }

    p2 = q0_run._p2(exe, case_dir, logs / "r4_qn0_p2.log", args.timeout)
    summary["p2"] = p2
    if p2["returncode"] != 0:
        summary["status"] = "P2_FAIL_R4_QN0"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_QN0_ROOT: {root}")
        print(f"ISSUE31_R4_QN0_STATUS: {summary['status']}")
        return 2

    runtime = q0_run._runtime(exe, case_dir, logs / "r4_qn0_runtime.log", args.timeout)
    summary["runtime"] = runtime
    if runtime["returncode"] != 0:
        summary["status"] = "R4_QN0_RUNTIME_FAIL"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_QN0_ROOT: {root}")
        print(f"ISSUE31_R4_QN0_STATUS: {summary['status']}")
        return 1

    invariants = issue91_run._checker(case_dir)
    summary["r3_invariants"] = invariants
    if invariants.get("pass") is not True:
        summary["status"] = "R4_QN0_R3_INVARIANT_FAIL"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_QN0_ROOT: {root}")
        print(f"ISSUE31_R4_QN0_STATUS: {summary['status']}")
        return 1

    physical = case_dir / "input_out.physical.csv"
    gauss = q0_run._gauss_evidence(physical)
    summary["gauss_law"] = gauss
    if gauss.get("status") != "MEASURED":
        summary["status"] = "R4_QN0_GAUSS_EVIDENCE_MISSING"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_QN0_ROOT: {root}")
        print(f"ISSUE31_R4_QN0_STATUS: {summary['status']}")
        return 1

    state = _state_evidence(physical)
    summary["state"] = state
    if state.get("status") != "MEASURED":
        summary["status"] = "R4_QN0_STATE_EVIDENCE_MISSING"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_QN0_ROOT: {root}")
        print(f"ISSUE31_R4_QN0_STATUS: {summary['status']}")
        return 1

    # QN0 is a controlled measurement.  It must demonstrate how the Poisson
    # state responds to physically balanced initialization before any feedback
    # acceptance threshold is frozen.
    summary["status"] = "R4_QN0_EVIDENCE_READY"
    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"ISSUE31_R4_QN0_ROOT: {root}")
    print(f"ISSUE31_R4_QN0_STATUS: {summary['status']}")
    print(f"ISSUE31_R4_QN0_REFERENCE_M3: {reference:.17g}")
    print(f"ISSUE31_R4_QN0_PHI_ABS_MAX_V: {state['phi_abs_max_V']:.17g}")
    print(f"ISSUE31_R4_QN0_VOLUME_CHARGE_C: {state['volume_charge_C']:.17g}")
    print(f"ISSUE31_R4_QN0_GAUSS_RELATIVE_DEFECT: {gauss['relative_defect']:.17g}")
    print(f"ISSUE31_R4_QN0_SUMMARY: {root / 'summary.json'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qpx", required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
