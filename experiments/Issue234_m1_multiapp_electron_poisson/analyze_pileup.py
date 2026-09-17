#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
files = sorted(ROOT.rglob("*electron_profile*.csv"))

if not files:
    raise SystemExit("no electron_profile CSV files found")

profiles = []
for path in files:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        continue

    def pick(row, *names):
        for name in names:
            if name in row and row[name] not in ("", None):
                return float(row[name])
        raise KeyError((path, names, tuple(row)))

    points = []
    for row in rows:
        x = pick(row, "x", "X")
        ne = pick(row, "electron_density_out")
        phi = pick(row, "potential_from_poisson")
        elem_id = int(float(row.get("id", len(points))))
        points.append((x, elem_id, ne, phi))

    points.sort(key=lambda p: p[0])
    peak = max(points, key=lambda p: p[2])
    right = points[-1]
    left = points[0]
    xmin, xmax = left[0], right[0]
    span = max(xmax - xmin, 1.0e-300)
    peak_fraction = (peak[0] - xmin) / span

    profiles.append({
        "file": str(path.relative_to(ROOT)),
        "n_points": len(points),
        "peak_x_m": peak[0],
        "peak_element_id": peak[1],
        "peak_ne_m3": peak[2],
        "peak_phi_V": peak[3],
        "right_x_m": right[0],
        "right_ne_m3": right[2],
        "right_phi_V": right[3],
        "left_ne_m3": left[2],
        "peak_position_fraction": peak_fraction,
        "peak_in_right_quarter": peak_fraction >= 0.75,
        "right_to_left_density_ratio": right[2] / max(left[2], 1.0e-300),
    })

if not profiles:
    raise SystemExit("electron_profile CSVs contained no rows")

summary = {
    "status": "MEASURED",
    "claim_scope": "diagnostic only: locate electron-density pile-up under lagged Poisson drift feedback",
    "profiles": profiles,
    "any_peak_in_right_quarter": any(p["peak_in_right_quarter"] for p in profiles),
    "largest_peak_ne_m3": max(p["peak_ne_m3"] for p in profiles),
}
(ROOT / "pileup_diagnostic_summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print(json.dumps(summary, indent=2, sort_keys=True))
