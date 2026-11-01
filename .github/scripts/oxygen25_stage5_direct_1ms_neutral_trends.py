#!/usr/bin/env python3
"""Scientific *diagnostic* only: report neutral density trends near 1 ms.

There is no steady-state or convergence certification here. The native
checkpoint and P0-P4 evidence are separately controlled by the workflow.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

FIELDS = {
    "O_3P": "n_O_3P_avg",
    "O_1D": "n_O_1D_avg",
    "O2_a1Delta": "n_O2_a_avg",
    "O2_X": "n_O2_X_avg",
}
TARGET_S = (0.0008, 0.0009, 0.001)
MAX_ABS_TIME_ERROR = 1.1e-5


def run(path: Path, destination: Path, power: int) -> dict:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) < 3:
        raise ValueError("insufficient native history rows")
    times = [float(row["time"]) for row in rows]
    if any(not math.isfinite(v) for v in times):
        raise ValueError("nonfinite simulation time")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("native CSV time is not strictly increasing")
    if not math.isclose(times[-1], 0.001, rel_tol=0, abs_tol=1e-15):
        raise ValueError("native simulation has not reached 1 ms")
    targets = []
    for wanted in TARGET_S:
        index = min(range(len(rows)), key=lambda k: abs(times[k] - wanted))
        if abs(times[index] - wanted) > MAX_ABS_TIME_ERROR:
            raise ValueError("time sampling too sparse for last-200us diagnosis")
        targets.append((times[index], rows[index]))
    species = {}
    for label, field in FIELDS.items():
        values = [float(r[field]) for _, r in targets]
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("nonfinite/negative neutral density")
        baseline_100 = values[1]
        baseline_200 = values[0]
        species[label] = {
            "field": field,
            "density_800us_m3": values[0],
            "density_900us_m3": values[1],
            "density_1000us_m3": values[2],
            "pct_change_900_to_1000us": None if baseline_100 == 0 else 100 * (values[2] / baseline_100 - 1),
            "pct_change_800_to_1000us": None if baseline_200 == 0 else 100 * (values[2] / baseline_200 - 1),
        }
    report = {
        "power_W": power,
        "input_csv": str(path),
        "requested_times_us": [800, 900, 1000],
        "actual_times_us": [t * 1e6 for t, _ in targets],
        "observables": species,
        "interpretation": "TREND_ONLY; steady state, timestep convergence, and physical accuracy NOT established",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    for name, value in species.items():
        print(name, "900-1000us change (%)", value["pct_change_900_to_1000us"], flush=True)
    print("OXYGEN25_STAGE5_DIRECT_NEUTRAL_TREND_DIAGNOSTICS_WRITTEN", destination, flush=True)
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--power-w", type=int, required=True, choices=(400, 1000))
    a = p.parse_args()
    run(a.csv, a.output, a.power_w)


if __name__ == "__main__":
    main()
