#!/usr/bin/env python3
"""Run the bounded Issue #31 R4-Q0 all-ground solved-Poisson discriminator."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from experiments.Issue91_real_qvt_r3 import run as issue91_run
from physics_harness.adapters.moose.nonlinear_solver import failure_signature, runtime_core_facts
from physics_harness.evidence import (
    create_collision_safe_directory,
    utc_timestamp,
    write_json_bundle,
)
from physics_harness.execution.cases import stage_case
from physics_harness.execution.runtime import resolve_executable, run_physics, validate_executable
from experiments.historical_recipe_support.issue31_r4 import build_r4_q0_input

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"


def _stage(target: Path) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text()
    input_text, meta = build_r4_q0_input(base)
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
    (target / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n"
    )
    return {
        "source": str(SOURCE.resolve()),
        "staging": staging,
        "construction": meta,
    }


def _p2(exe: Path, case_dir: Path, log: Path, timeout: float) -> dict[str, Any]:
    result = run_physics(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=log,
        extra_args=("--check-input",),
        timeout_seconds=timeout,
    )
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "log": str(log),
    }


def _runtime(exe: Path, case_dir: Path, log: Path, timeout: float) -> dict[str, Any]:
    result = run_physics(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=log,
        extra_args=("-snes_monitor", "-snes_converged_reason", "-ksp_converged_reason"),
        timeout_seconds=timeout,
    )
    text = log.read_text(errors="replace")
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "failure_signature": failure_signature(text),
        "runtime_facts": runtime_core_facts(
            text,
            returncode=result.returncode,
            coupled_scaling_variables=("n_e", "potential_plasma"),
        ),
        "log": str(log),
    }


def _gauss_evidence(csv_path: Path) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"status": "MISSING", "error": "physical CSV has no rows"}
    row = rows[-1]
    required = ("r31_charge_integral", "r31_gauss_flux_charge")
    missing = [name for name in required if name not in row]
    if missing:
        return {
            "status": "MISSING",
            "error": f"missing Gauss-law columns: {missing}",
        }
    try:
        q_volume = float(row["r31_charge_integral"])
        q_flux = float(row["r31_gauss_flux_charge"])
        time = float(row["time"])
    except (TypeError, ValueError) as exc:
        return {"status": "INVALID", "error": str(exc)}
    defect = q_flux - q_volume
    scale = max(abs(q_volume), abs(q_flux), 1.0e-300)
    return {
        "status": "MEASURED",
        "time": time,
        "volume_charge_C": q_volume,
        "boundary_displacement_flux_C": q_flux,
        "signed_defect_C": defect,
        "absolute_defect_C": abs(defect),
        "relative_defect": abs(defect) / scale,
        "sign_convention": (
            "SideDiffusiveFluxIntegral = integral(-eps_r*grad(phi).n)dA; "
            "scaled by eps0, so compare directly with integral(rho_q)dV"
        ),
        "acceptance": "UNSET_FIRST_CONTROL_MEASUREMENT",
    }


def run(args: argparse.Namespace) -> int:
    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        args.results_root,
        f"issue31_r4_q0_all_ground_{stamp}",
    )
    case_dir = root / "case"
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    staged = _stage(case_dir)
    summary: dict[str, Any] = {
        "issue": 31,
        "experiment": "r4-q0-all-ground-volume-charge-poisson",
        "repository_head": issue91_run._repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": issue91_run._sha256(exe),
        "phase": {
            "volume_charge": True,
            "poisson": True,
            "electrostatic_feedback": False,
            "surface_accumulated_charge": False,
            "all_ground_phi": True,
        },
        "staged": staged,
        "p2": {},
        "runtime": {},
        "r3_invariants": {},
        "gauss_law": {},
        "status": "NOT_RUN",
    }

    p2 = _p2(exe, case_dir, logs / "r4_q0_p2.log", args.timeout)
    summary["p2"] = p2
    if p2["returncode"] != 0:
        summary["status"] = "P2_FAIL_R4_Q0"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_Q0_ROOT: {root}")
        print(f"ISSUE31_R4_Q0_STATUS: {summary['status']}")
        return 2

    runtime = _runtime(exe, case_dir, logs / "r4_q0_runtime.log", args.timeout)
    summary["runtime"] = runtime
    if runtime["returncode"] != 0:
        summary["status"] = "R4_Q0_RUNTIME_FAIL"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_Q0_ROOT: {root}")
        print(f"ISSUE31_R4_Q0_STATUS: {summary['status']}")
        return 1

    invariants = issue91_run._checker(case_dir)
    summary["r3_invariants"] = invariants
    if invariants.get("pass") is not True:
        summary["status"] = "R4_Q0_R3_INVARIANT_FAIL"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_Q0_ROOT: {root}")
        print(f"ISSUE31_R4_Q0_STATUS: {summary['status']}")
        return 1

    physical = case_dir / "input_out.physical.csv"
    gauss = _gauss_evidence(physical)
    summary["gauss_law"] = gauss
    if gauss.get("status") != "MEASURED":
        summary["status"] = "R4_Q0_GAUSS_EVIDENCE_MISSING"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_Q0_ROOT: {root}")
        print(f"ISSUE31_R4_Q0_STATUS: {summary['status']}")
        return 1

    # First Q0 establishes the numerical Gauss-law defect scale.  Do not invent
    # a universal relative tolerance before this controlled measurement exists.
    summary["status"] = "R4_Q0_EVIDENCE_READY"
    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"ISSUE31_R4_Q0_ROOT: {root}")
    print(f"ISSUE31_R4_Q0_STATUS: {summary['status']}")
    print(f"ISSUE31_R4_Q0_GAUSS_RELATIVE_DEFECT: {gauss['relative_defect']:.17g}")
    print(f"ISSUE31_R4_Q0_SUMMARY: {root / 'summary.json'}")
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
