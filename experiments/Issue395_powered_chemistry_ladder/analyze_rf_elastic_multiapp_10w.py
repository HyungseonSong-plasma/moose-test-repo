#!/usr/bin/env python3
"""Analyze the Issue #395 continuous RF+EI02 MultiApp 10 W diagnostic."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import analyze_rf_elastic_multiapp as base

TARGET_W = 10.0


def output_path(argv: list[str]) -> Path | None:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--output", type=Path)
    ns, _ = ap.parse_known_args(argv)
    return ns.output


def main() -> int:
    out = output_path(sys.argv[1:])
    base.TARGET_W = TARGET_W
    rc = base.main()

    if out is not None and out.exists():
        report = json.loads(out.read_text(encoding="utf-8"))
        report["gate"] = "single-execution plasma-Maxwell MultiApp + EI02 elastic + 10 W absorbed-RF PID"
        report["architecture"]["soft_start"] = (
            "10 W low-power initialization from validated 1000 W coil-amplitude calibration"
        )
        report["power"]["target_W"] = TARGET_W
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("ISSUE395_RF_ELASTIC_MULTIAPP_10W_ANALYSIS")
        print(json.dumps(report, indent=2, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
