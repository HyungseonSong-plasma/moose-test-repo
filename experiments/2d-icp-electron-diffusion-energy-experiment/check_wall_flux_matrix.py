#!/usr/bin/env python3
"""Compare native and controlled electron-energy wall-flux closures."""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

INITIAL_TE_EV = (2.0 / 3.0) * 5.73276
LABELS = ["native_4over3", "functor_4over3", "matched_5over3"]


def find_one(root: Path, label: str, pattern: str) -> Path:
    candidates = sorted((root / f"electron-energy-wall-{label}").rglob(pattern))
    if len(candidates) != 1:
        raise SystemExit(
            f"{label}: expected exactly one {pattern}; got {len(candidates)}: {candidates}"
        )
    return candidates[0]


def load_profile(path: Path):
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"empty profile: {path}")
    needed = {"id", "x", "y", "electron_density", "electron_temperature_eV"}
    missing = needed - set(rows[0])
    if missing:
        raise SystemExit(f"{path}: missing columns {sorted(missing)}")
    out = {}
    for row in rows:
        eid = int(row["id"])
        vals = {
            "x": float(row["x"]),
            "y": float(row["y"]),
            "ne": float(row["electron_density"]),
            "te": float(row["electron_temperature_eV"]),
        }
        if any(not math.isfinite(v) for v in vals.values()):
            raise SystemExit(f"{path}: non-finite values at element {eid}")
        out[eid] = vals
    return out


root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("wall-flux-artifacts")
profiles = {
    label: load_profile(find_one(root, label, "electron_diffusion_final_profile_*.csv"))
    for label in LABELS
}

ids = sorted(profiles[LABELS[0]])
for label, profile in profiles.items():
    if sorted(profile) != ids:
        raise SystemExit(f"{label}: element IDs differ")
    for eid in ids:
        ref = profiles[LABELS[0]][eid]
        cur = profile[eid]
        if abs(cur["x"] - ref["x"]) > 1.0e-12 or abs(cur["y"] - ref["y"]) > 1.0e-12:
            raise SystemExit(f"{label}: coordinate mismatch at element {eid}")

summary = []
for label in LABELS:
    p = profiles[label]
    max_id = max(ids, key=lambda eid: p[eid]["te"])
    min_id = min(ids, key=lambda eid: p[eid]["te"])
    summary.append(
        {
            "label": label,
            "te_min_eV": p[min_id]["te"],
            "te_max_eV": p[max_id]["te"],
            "bump_max_eV": p[max_id]["te"] - INITIAL_TE_EV,
            "max_id": max_id,
            "max_r_m": p[max_id]["x"],
            "max_z_m": p[max_id]["y"],
            "min_id": min_id,
            "min_r_m": p[min_id]["x"],
            "min_z_m": p[min_id]["y"],
        }
    )


def delta(a: str, b: str):
    pa = profiles[a]
    pb = profiles[b]
    te = [pa[eid]["te"] - pb[eid]["te"] for eid in ids]
    ne = [pa[eid]["ne"] - pb[eid]["ne"] for eid in ids]
    return {
        "a": a,
        "b": b,
        "te_linf_eV": max(abs(v) for v in te),
        "te_rms_eV": math.sqrt(sum(v * v for v in te) / len(te)),
        "ne_linf_m3": max(abs(v) for v in ne),
        "ne_rms_m3": math.sqrt(sum(v * v for v in ne) / len(ne)),
    }

comparisons = [
    delta("native_4over3", "functor_4over3"),
    delta("native_4over3", "matched_5over3"),
    delta("functor_4over3", "matched_5over3"),
]

out = {
    "initial_te_eV": INITIAL_TE_EV,
    "profiles": summary,
    "comparisons": comparisons,
}
Path("wall_flux_comparison.json").write_text(
    json.dumps(out, indent=2, sort_keys=True) + "\n"
)
with Path("wall_flux_comparison.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(summary[0].keys()))
    writer.writeheader()
    writer.writerows(summary)

print("ELECTRON_ENERGY_WALL_FLUX_COMPARISON=PASS")
print(json.dumps(out, indent=2, sort_keys=True))
