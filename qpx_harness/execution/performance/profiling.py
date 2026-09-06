"""Canonical one-step QPX performance profiling orchestration.

External-format configuration is adapter-owned. This module retains run
orchestration and result composition only.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from qpx_harness.adapters.moose.performance.profile import (
    find_metrics_csv,
    read_last_metrics_row,
    write_overlay,
)
from qpx_harness.adapters.petsc.performance import event_hints, profile_arguments

from ...evidence import ensure_fresh_directory, sha256_file
from ..runtime import resolve_executable, run_qpx, validate_executable


def profile_case(
    *,
    case_dir: Path,
    input_name: str,
    label: str,
    executable: str | Path | None = None,
    out_dir: Path | None = None,
    issue: int | None = None,
    prefix: str = "qpxh",
    output_namespace: str = "profiles",
    num_steps: int = 1,
    nl_max_its: int | None = None,
    abort_on_solve_fail: bool = False,
) -> int:
    case_dir = Path(case_dir).expanduser().resolve()
    if not case_dir.is_dir():
        raise SystemExit(f"case directory does not exist: {case_dir}")

    input_path = (case_dir / input_name).resolve()
    if case_dir not in input_path.parents and input_path.parent != case_dir:
        raise SystemExit("input must resolve inside case_dir")
    if not input_path.is_file():
        raise SystemExit(f"input does not exist: {input_path}")

    exe = resolve_executable(executable)
    validate_executable(exe)

    if out_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or "case"
        out_dir = case_dir / output_namespace / f"{safe_label}_{stamp}"
    out_dir = Path(out_dir).expanduser().resolve()
    ensure_fresh_directory(out_dir)

    overlay = out_dir / f"{prefix}_profile_overlay.i"
    metrics_base = out_dir / f"{prefix}_metrics"
    petsc_csv = out_dir / "petsc_log.csv"
    p2_log = out_dir / "p2_check_input.log"
    p3_log = out_dir / "p3_run.log"
    bounded_executioner_overlay = write_overlay(
        overlay,
        metrics_base,
        prefix=prefix,
        nl_max_its=nl_max_its,
        abort_on_solve_fail=abort_on_solve_fail,
    )

    common_extra = [str(overlay), f"Executioner/num_steps={num_steps}"]
    print("P2 START   : qpx-opt --check-input with diagnostic overlay")
    p2 = run_qpx(
        exe,
        cwd=case_dir,
        input_name=input_name,
        log_path=p2_log,
        extra_args=[*common_extra, "--check-input"],
    )
    print("P2 RESULT  :", "PASS" if p2.returncode == 0 else f"FAIL rc={p2.returncode}")
    if p2.returncode != 0:
        summary = {
            "issue": issue,
            "label": label,
            "metric_prefix": prefix,
            "classification": "HARNESS_OR_CONSTRUCTION_FAIL",
            "qpx_realpath": str(exe),
            "case_dir": str(case_dir),
            "input": input_name,
            "input_sha256": sha256_file(input_path),
            "overlay_sha256": sha256_file(overlay),
            "bounded_executioner_overlay": bounded_executioner_overlay,
            "p2_returncode": p2.returncode,
            "p2_log": str(p2_log),
        }
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        return p2.returncode or 2

    p3_extra = [*common_extra, *profile_arguments(petsc_csv)]
    print("CASE START :", datetime.now(timezone.utc).isoformat())
    p3 = run_qpx(
        exe,
        cwd=case_dir,
        input_name=input_name,
        log_path=p3_log,
        extra_args=p3_extra,
        stream=True,
    )
    print(
        "CASE END   :",
        datetime.now(timezone.utc).isoformat(),
        f"rc={p3.returncode} wall_s={p3.wall_seconds:.6f}",
    )

    metrics_csv = find_metrics_csv(metrics_base)
    last_metrics = read_last_metrics_row(metrics_csv)
    bounded_diagnostic = bool(bounded_executioner_overlay.strip())
    bounded_capture = (
        bounded_diagnostic
        and abort_on_solve_fail
        and nl_max_its is not None
        and petsc_csv.is_file()
    )
    if p3.returncode == 0:
        classification = "PROFILE_CAPTURED"
    elif bounded_capture:
        classification = "BOUNDED_PROFILE_CAPTURED"
    else:
        classification = "RUNTIME_FAIL_OR_NONCONVERGENCE"

    summary = {
        "issue": issue,
        "label": label,
        "metric_prefix": prefix,
        "classification": classification,
        "qpx_realpath": str(exe),
        "case_dir": str(case_dir),
        "input": input_name,
        "input_sha256": sha256_file(input_path),
        "overlay_sha256": sha256_file(overlay),
        "one_step_override": f"Executioner/num_steps={num_steps}",
        "bounded_diagnostic": bounded_diagnostic,
        "bounded_executioner_overlay": bounded_executioner_overlay,
        "nl_max_its_override": nl_max_its,
        "abort_on_solve_fail_override": abort_on_solve_fail,
        "physics_parameters_changed": False,
        "solver_tolerances_changed": False,
        "scientific_acceptance_eligible": not bounded_diagnostic,
        "p2_returncode": p2.returncode,
        "p3_returncode": p3.returncode,
        "wall_seconds": p3.wall_seconds,
        "metrics_csv": str(metrics_csv) if metrics_csv else None,
        "last_metrics_row": last_metrics,
        "perfgraph_log": str(p3_log),
        "petsc_log_csv": str(petsc_csv),
        "petsc_event_hints": event_hints(petsc_csv),
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    print("QPX PROFILE SUMMARY:")
    print(f"  OUTPUT_DIR : {out_dir}")
    print(f"  CLASS      : {classification}")
    print(f"  WALL_S     : {p3.wall_seconds:.6f}")
    print(f"  P3_RC      : {p3.returncode}")
    print(f"  SUMMARY    : {summary_path}")
    print(f"  PERFGRAPH  : {p3_log}")
    print(f"  PETSC_CSV  : {petsc_csv}")
    return 0 if p3.returncode == 0 or bounded_capture else p3.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--qpx")
    parser.add_argument("--out-dir")
    parser.add_argument("--issue", type=int)
    parser.add_argument("--prefix", default="qpxh")
    parser.add_argument("--output-namespace", default="profiles")
    parser.add_argument("--num-steps", type=int, default=1)
    parser.add_argument("--nl-max-its", type=int, help="diagnostic-only nonlinear-iteration cap for bounded profile capture")
    parser.add_argument("--abort-on-solve-fail", action="store_true", help="abort after bounded nonlinear nonconvergence instead of timestep cutback")
    args = parser.parse_args(argv)
    return profile_case(
        case_dir=Path(args.case_dir),
        input_name=args.input,
        label=args.label,
        executable=args.qpx,
        out_dir=Path(args.out_dir) if args.out_dir else None,
        issue=args.issue,
        prefix=args.prefix,
        output_namespace=args.output_namespace,
        num_steps=args.num_steps,
        nl_max_its=args.nl_max_its,
        abort_on_solve_fail=args.abort_on_solve_fail,
    )


if __name__ == "__main__":
    raise SystemExit(main())
