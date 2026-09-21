#!/usr/bin/env python3
from __future__ import annotations
import csv
import importlib.util
import json
import math
import sys
from pathlib import Path

SPECIES = ["O2","O2s","O2p","O","Om","Op","Os"]
NEUTRAL = ["O2","O2s","O","Os"]
CHARGED = ["O2p","Om","Op"]
ORACLE_REL_TOL = 2.0e-5

if len(sys.argv) != 3:
    raise SystemExit("usage: check.py input_out.csv prepare_evidence.json")

csv_path = Path(sys.argv[1])
evidence_path = Path(sys.argv[2])
case = Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location("r14_oracle", case/"oracle.py")
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)

fail = []

if not evidence_path.is_file():
    fail.append("missing prepare_evidence.json")
else:
    ev = json.loads(evidence_path.read_text())
    if ev.get("status") != "PASS":
        fail.append(f"prepare evidence status is {ev.get('status')}")
    if ev.get("failures"):
        fail.append(f"prepare evidence contains failures: {ev.get('failures')}")

if not csv_path.is_file():
    fail.append(f"missing runtime CSV: {csv_path}")
    rows = []
else:
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        fail.append("runtime CSV contains no rows")

if rows:
    row = rows[-1]
    runtime = {"A":{}, "B":{}}

    for tag in ("A","B"):
        for s in SPECIES:
            col = f"Dmix_{tag}_{s}"
            try:
                value = float(row[col])
            except Exception as e:
                fail.append(f"missing/non-numeric {col}: {e}")
                continue
            runtime[tag][s] = value
            if not math.isfinite(value) or value <= 0.0:
                fail.append(f"{col} is not finite positive: {value}")

    expected = {
        "A": oracle.evaluate(case/"transport_data.txt", oracle.NE_A),
        "B": oracle.evaluate(case/"transport_data.txt", oracle.NE_B),
    }

    for tag in ("A","B"):
        print(f"--- CASE {tag} ---")
        for s in SPECIES:
            if s not in runtime[tag]:
                continue
            got = runtime[tag][s]
            exp = expected[tag][s]
            rel = abs(got-exp)/max(abs(exp),1e-300)
            print(f"{s:3s} runtime={got:.17e} oracle={exp:.17e} rel={rel:.6e}")
            if rel > ORACLE_REL_TOL:
                fail.append(
                    f"oracle parity failed {tag}/{s}: rel={rel:.6e} > {ORACLE_REL_TOL:.1e}"
                )

    # Electron density must not affect pairs of a neutral species with the other
    # species through the charged-charged path.
    for s in NEUTRAL:
        if s in runtime["A"] and s in runtime["B"]:
            rel = abs(runtime["B"][s]-runtime["A"][s])/runtime["A"][s]
            print(f"NEUTRAL_NE_INVARIANCE {s}: rel={rel:.6e}")
            if rel > 1e-12:
                fail.append(f"neutral ne invariance failed for {s}: {rel:.6e}")

    # Charged Dmix must demonstrate dynamic-screening sensitivity.
    min_sensitivity = float("inf")
    for s in CHARGED:
        if s in runtime["A"] and s in runtime["B"]:
            rel = abs(runtime["B"][s]-runtime["A"][s])/runtime["A"][s]
            min_sensitivity = min(min_sensitivity, rel)
            print(f"CHARGED_NE_SENSITIVITY {s}: rel={rel:.6e}")
            if rel < 0.05:
                fail.append(f"charged ne sensitivity too small for {s}: {rel:.6e}")
    if math.isfinite(min_sensitivity):
        print(f"MIN_CHARGED_NE_SENSITIVITY={min_sensitivity:.6e}")

print("="*78)
if fail:
    print("R14_EVR1B_DMIX_ORACLE_RUNTIME: FAIL")
    for x in fail:
        print("  -",x)
    raise SystemExit(1)

print(f"ORACLE_REL_TOL={ORACLE_REL_TOL:.1e}")
print("R14_EVR1B_DMIX_ORACLE_RUNTIME: PASS")
print("EVR_CREDIT: NONE — EVR1-B tranche only; parent EVR1 not yet accepted")
