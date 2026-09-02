"""Reusable one-step QPX performance profiling."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .evidence import ensure_fresh_directory, sha256_file
from .execution.runtime import resolve_executable, run_qpx, validate_executable


def _quote_hit_path(path: Path) -> str:
    text = str(path)
    if "'" in text:
        raise SystemExit(f"output path contains unsupported single quote: {path}")
    return f"'{text}'"


def write_overlay(path: Path, metrics_base: Path, *, prefix: str = "qpxh") -> None:
    path.write_text(
        f"""# Generated QPX profiling overlay.
# Diagnostics only: no physics, dt, tolerance, or solver-type changes.

[Postprocessors]
  [{prefix}_num_dofs]
    type = NumDOFs
    system = NL
    execute_on = 'initial timestep_end'
  []
  [{prefix}_nonlinear_iterations]
    type = NumNonlinearIterations
    execute_on = timestep_end
  []
  [{prefix}_linear_iterations]
    type = NumLinearIterations
    execute_on = timestep_end
  []
  [{prefix}_residual_evaluations]
    type = NumResidualEvaluations
    execute_on = timestep_end
  []
[]

[Outputs]
  [{prefix}_perfgraph]
    type = PerfGraphOutput
    execute_on = final
    level = 3
    heaviest_branch = true
    heaviest_sections = 40
  []
  [{prefix}_metrics]
    type = CSV
    file_base = {_quote_hit_path(metrics_base)}
    show = '{prefix}_num_dofs {prefix}_nonlinear_iterations {prefix}_linear_iterations {prefix}_residual_evaluations'
    execute_on = 'initial timestep_end'
  []
[]
"""
    )


def find_metrics_csv(metrics_base: Path) -> Path | None:
    direct = Path(str(metrics_base) + ".csv")
    if direct.is_file():
        return direct
    matches = sorted(metrics_base.parent.glob(metrics_base.name + "*.csv"))
    return matches[0] if matches else None


def read_last_metrics_row(csv_path: Path | None) -> dict[str, str] | None:
    if csv_path is None or not csv_path.is_file():
        return None
    try:
        with csv_path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
    except Exception:
        return None
    return rows[-1] if rows else None


def petsc_event_hint(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.is_file():
        return []
    wanted = re.compile(
        r"KSPSolve|SNES|PCSetUp|MatLUFactor|MatCholeskyFactor|MatAssembly|MatSolve|Factor",
        re.IGNORECASE,
    )
    hits: list[dict[str, str]] = []
    try:
        with csv_path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                joined = " ".join(str(value) for value in row.values())
                if wanted.search(joined):
                    hits.append({k: v for k, v in row.items() if v not in (None, "")})
    except Exception:
        return []
    return hits[:80]


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
    write_overlay(overlay, metrics_base, prefix=prefix)

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
            "p2_returncode": p2.returncode,
            "p2_log": str(p2_log),
        }
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        return p2.returncode or 2

    p3_extra = [
        *common_extra,
        "-log_view",
        f":{petsc_csv}:ascii_csv",
        "-log_view_memory",
        "-snes_converged_reason",
        "-ksp_converged_reason",
    ]
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
    summary = {
        "issue": issue,
        "label": label,
        "metric_prefix": prefix,
        "classification": "PROFILE_CAPTURED"
        if p3.returncode == 0
        else "RUNTIME_FAIL_OR_NONCONVERGENCE",
        "qpx_realpath": str(exe),
        "case_dir": str(case_dir),
        "input": input_name,
        "input_sha256": sha256_file(input_path),
        "overlay_sha256": sha256_file(overlay),
        "one_step_override": f"Executioner/num_steps={num_steps}",
        "physics_parameters_changed": False,
        "solver_tolerances_changed": False,
        "p2_returncode": p2.returncode,
        "p3_returncode": p3.returncode,
        "wall_seconds": p3.wall_seconds,
        "metrics_csv": str(metrics_csv) if metrics_csv else None,
        "last_metrics_row": last_metrics,
        "perfgraph_log": str(p3_log),
        "petsc_log_csv": str(petsc_csv),
        "petsc_event_hints": petsc_event_hint(petsc_csv),
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    print("QPX PROFILE SUMMARY:")
    print(f"  OUTPUT_DIR : {out_dir}")
    print(f"  WALL_S     : {p3.wall_seconds:.6f}")
    print(f"  P3_RC      : {p3.returncode}")
    print(f"  SUMMARY    : {summary_path}")
    print(f"  PERFGRAPH  : {p3_log}")
    print(f"  PETSC_CSV  : {petsc_csv}")
    return p3.returncode


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
    )


if __name__ == "__main__":
    raise SystemExit(main())
