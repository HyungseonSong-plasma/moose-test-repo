#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue211_science_factorial import run as sci
from experiments.Issue228_drift_gradient_compare import run as cmp

MODES = ("limit_050", "limit_100")


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--physics-opt", type=Path, required=True)
    p.add_argument("--mode", choices=MODES, required=True)
    p.add_argument("--results-root", type=Path, required=True)
    p.add_argument("--timeout", type=float, default=300.0)
    args = p.parse_args()

    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    text, meta = cmp.build_case(args.mode)
    case_dir = out / "case"
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stage = sci._stage(case_dir, text, meta)
    p2 = s5r._p2(args.physics_opt.resolve(), case_dir, logs / "p2.log", timeout=min(args.timeout, 180.0))
    summary = {"mode": args.mode, "stage": stage, "p2": p2}
    if p2.get("returncode") != 0:
        summary["status"] = "P2_FAIL"
        write(out / "summary.json", summary)
        return 2
    runtime = sci._runtime(args.physics_opt.resolve(), case_dir, logs / "runtime.log", logs / "time_v.log", args.timeout)
    summary["runtime"] = runtime
    try:
        summary["result"] = cmp._case_result(case_dir, text, meta, runtime)
        summary["status"] = "PASS" if summary["result"]["runtime_returncode"] == 0 else "FAIL"
    except Exception as exc:
        summary["status"] = "ANALYSIS_FAIL"
        summary["analysis_error"] = f"{type(exc).__name__}: {exc}"
    write(out / "summary.json", summary)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
