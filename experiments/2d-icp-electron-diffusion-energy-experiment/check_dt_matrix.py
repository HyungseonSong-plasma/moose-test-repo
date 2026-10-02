#!/usr/bin/env python3
"""Aggregate electron-temperature timestep-matrix profiles."""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

INITIAL_TE_EV = (2.0 / 3.0) * 5.73276
EXPECTED_LABELS = ["dt1ns", "dt0p5ns", "dt0p25ns", "dt0p125ns"]
DT_S = {
    "dt1ns": 1.0e-9,
    "dt0p5ns": 5.0e-10,
    "dt0p25ns": 2.5e-10,
    "dt0p125ns": 1.25e-10,
}


def find_profile(root: Path, label: str) -> Path:
    candidates = sorted((root / f"electron-energy-dt-{label}").rglob("electron_diffusion_final_profile_*.csv"))
    if len(candidates) != 1:
        raise SystemExit(
            f"{label}: expected exactly one final profile CSV; "
            f"got {len(candidates)}: {candidates}"
        )
    return candidates[0]


def load_profile(path: Path):
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"empty profile: {path}")
    required = {"id", "x", "y", "electron_density", "electron_temperature_eV"}
    missing = required - set(rows[0])
    if missing:
        raise SystemExit(f"{path}: missing columns {sorted(missing)}")
    parsed = {}
    for row in rows:
        eid = int(row["id"])
        values = {
            "x": float(row["x"]),
            "y": float(row["y"]),
            "ne": float(row["electron_density"]),
            "te": float(row["electron_temperature_eV"]),
        }
        if any(not math.isfinite(v) for v in values.values()):
            raise SystemExit(f"{path}: non-finite row for id={eid}")
        if values["ne"] <= 0.0 or values["te"] <= 0.0:
            raise SystemExit(f"{path}: non-positive physical field for id={eid}: {values}")
        parsed[eid] = values
    return parsed


root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dt-matrix-artifacts")
profiles = {label: load_profile(find_profile(root, label)) for label in EXPECTED_LABELS}

ids = sorted(profiles[EXPECTED_LABELS[-1]])
for label, profile in profiles.items():
    if sorted(profile) != ids:
        raise SystemExit(f"{label}: element-id set differs from finest timestep")
    for eid in ids:
        ref = profiles[EXPECTED_LABELS[-1]][eid]
        cur = profile[eid]
        if abs(cur["x"] - ref["x"]) > 1.0e-12 or abs(cur["y"] - ref["y"]) > 1.0e-12:
            raise SystemExit(f"{label}: coordinate mismatch at element {eid}")

summary = []
for label in EXPECTED_LABELS:
    p = profiles[label]
    max_id = max(ids, key=lambda eid: p[eid]["te"])
    min_id = min(ids, key=lambda eid: p[eid]["te"])
    te_max = p[max_id]["te"]
    te_min = p[min_id]["te"]
    summary.append(
        {
            "label": label,
            "dt_s": DT_S[label],
            "te_min_eV": te_min,
            "te_max_eV": te_max,
            "bump_max_eV": te_max - INITIAL_TE_EV,
            "max_id": max_id,
            "max_r_m": p[max_id]["x"],
            "max_z_m": p[max_id]["y"],
            "min_id": min_id,
            "min_r_m": p[min_id]["x"],
            "min_z_m": p[min_id]["y"],
        }
    )

finest = profiles[EXPECTED_LABELS[-1]]
for item in summary:
    p = profiles[item["label"]]
    diffs = [p[eid]["te"] - finest[eid]["te"] for eid in ids]
    item["linf_vs_finest_eV"] = max(abs(v) for v in diffs)
    item["rms_vs_finest_eV"] = math.sqrt(sum(v * v for v in diffs) / len(diffs))

pairwise = []
for coarse, fine in zip(EXPECTED_LABELS[:-1], EXPECTED_LABELS[1:]):
    pc = profiles[coarse]
    pf = profiles[fine]
    diffs = [pc[eid]["te"] - pf[eid]["te"] for eid in ids]
    pairwise.append(
        {
            "coarse": coarse,
            "fine": fine,
            "linf_eV": max(abs(v) for v in diffs),
            "rms_eV": math.sqrt(sum(v * v for v in diffs) / len(diffs)),
        }
    )

for i in range(1, len(pairwise)):
    prev = pairwise[i - 1]["linf_eV"]
    cur = pairwise[i]["linf_eV"]
    pairwise[i]["linf_refinement_ratio"] = prev / cur if cur > 0.0 else math.inf

out = {"initial_te_eV": INITIAL_TE_EV, "profiles": summary, "pairwise": pairwise}
Path("dt_matrix_summary.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")

with Path("dt_matrix_summary.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(summary[0].keys()))
    writer.writeheader()
    writer.writerows(summary)

print("ELECTRON_ENERGY_DT_MATRIX=PASS")
print(json.dumps(out, indent=2, sort_keys=True))
