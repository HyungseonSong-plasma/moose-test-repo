#!/usr/bin/env python3
"""Analyze Issue #395 continuous 100 W RF + EI02 elastic + O2 dissociation to 15 us."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import analyze_rf_elastic_diss_multiapp_100w as base

FINAL_TIME = 1.5e-5
POWER_SETTLING_TIME = 1.0e-7


def output_path(argv: list[str]) -> Path | None:
    import argparse

    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--output", type=Path)
    ns, _ = ap.parse_known_args(argv)
    return ns.output


def main() -> int:
    out = output_path(sys.argv[1:])

    # Preserve the 100 W chemistry contract but qualify the long trajectory
    # after the already-observed 0-100 ns power-controller startup transient.
    base.FINAL_TIME = FINAL_TIME
    base.base.FINAL_TIME = FINAL_TIME
    base.base.POWER_SETTLING_TIME = POWER_SETTLING_TIME

    rc = base.main()

    if out is not None and out.exists():
        report = json.loads(out.read_text(encoding="utf-8"))
        failures = list(report.get("failures", []))
        report["gate"] = (
            "single-execution plasma-Maxwell MultiApp + EI02 elastic + source-backed O2 dissociation "
            "+ 100 W absorbed-RF PID, 0-15 us"
        )
        report["classification"] = (
            "ISSUE395_RF_ELASTIC_DISS_MULTIAPP_15US_PASS"
            if not failures
            else "ISSUE395_RF_ELASTIC_DISS_MULTIAPP_15US_FAIL"
        )
        report["status"] = "PASS" if not failures else "FAIL"
        report["power"]["settling_time_s"] = POWER_SETTLING_TIME
        report["final"]["requested_final_time_s"] = FINAL_TIME
        report["trajectory"] = {
            "requested_final_time_s": FINAL_TIME,
            "power_regulation_gate_starts_s": POWER_SETTLING_TIME,
            "time_grid": "accepted staged 15 us TimeSequenceStepper: 1 ns -> 10 ns -> 100 ns -> 1 us",
        }
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("ISSUE395_RF_ELASTIC_DISS_MULTIAPP_100W_15US_ANALYSIS")
        print(json.dumps(report, indent=2, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
