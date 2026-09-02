#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

SPECIES = ["O2", "O2s", "O2p", "O", "Om", "Op", "Os"]

if len(sys.argv) != 3:
    raise SystemExit("usage: check.py input_out.csv prepare_evidence.json")

csv_path = Path(sys.argv[1])
evidence_path = Path(sys.argv[2])

failures = []

if not evidence_path.is_file():
    failures.append(f"missing prepare evidence: {evidence_path}")
    evidence = {}
else:
    evidence = json.loads(evidence_path.read_text())
    if evidence.get("status") != "PASS":
        failures.append("prepare_evidence status is not PASS")
    if evidence.get("failures"):
        failures.append(f"prepare evidence reports failures: {evidence.get('failures')}")
    expected_db_sha = "2fa7988c79f6ea23ebdd50e6d1d7fc5018dc8854a27459511ec95c94ebe7ff3d"
    got_db_sha = evidence.get("transport_data_sha256")
    if got_db_sha != expected_db_sha:
        failures.append(
            f"prepare evidence transport-data SHA mismatch: {got_db_sha} != {expected_db_sha}"
        )

if not csv_path.is_file():
    failures.append(f"missing runtime CSV: {csv_path}")
    rows = []
else:
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        failures.append("runtime CSV contains no rows")

if rows:
    r = rows[-1]

    dmix = {}
    dt = {}
    kt = {}

    for s in SPECIES:
        for prefix, store in [("D_mix", dmix), ("D_T", dt), ("kT", kt)]:
            col = f"{prefix}_{s}"
            if col not in r:
                failures.append(f"missing runtime column {col}")
                continue
            try:
                value = float(r[col])
            except Exception:
                failures.append(f"non-numeric runtime value {col}={r[col]!r}")
                continue
            if not math.isfinite(value):
                failures.append(f"non-finite runtime value {col}={value}")
            store[s] = value

    if len(dmix) == 7:
        for s, value in dmix.items():
            print(f"D_mix_{s}={value:.17e}")
            if not value > 0.0:
                failures.append(f"D_mix_{s} is not positive: {value}")

        vals = list(dmix.values())
        if min(vals) > 0:
            spread = max(vals) / min(vals)
            print(f"D_mix_spread=max/min={spread:.9e}")
            if spread <= 1.001:
                failures.append(
                    "D_mix outputs are effectively common across all species; "
                    "expected species-dependent mixture-averaged coefficients"
                )

    if len(dt) == 7:
        for s, value in dt.items():
            print(f"D_T_{s}={value:.17e}")
        max_abs_dt = max(abs(v) for v in dt.values())
        print(f"max_abs_D_T={max_abs_dt:.9e}")
        if max_abs_dt <= 1e-30:
            failures.append(
                "all D_T outputs are numerically zero; runtime thermal-diffusion "
                "coefficient path was not demonstrated"
            )

    if len(kt) == 7:
        for s, value in kt.items():
            print(f"kT_{s}={value:.17e}")

print("=" * 78)
if failures:
    print("R14_EVR1A_RUNTIME_PROBE: FAIL")
    for f in failures:
        print("  -", f)
    print("CLASSIFICATION: construction/data/representation/runtime until localized")
    raise SystemExit(1)

print("R14_EVR1A_RUNTIME_PROBE: PASS")
print("EVR_CREDIT: NONE — this is EVR1-A material-runtime evidence, not full EVR1")
raise SystemExit(0)
