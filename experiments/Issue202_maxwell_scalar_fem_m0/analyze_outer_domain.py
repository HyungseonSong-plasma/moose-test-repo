#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

CASE = Path(__file__).resolve().parent
OUT = CASE / "results_outer"
FACTORS = (1, 2, 4, 8)
PROBES = (
    "E_imag_probe_r05",
    "E_imag_probe_r10",
    "E_imag_probe_r15",
    "E_imag_probe_r20",
    "E_imag_probe_upper_r05",
    "E_imag_probe_upper_r12",
    "E_imag_probe_upper_r18",
)
BASELINE_TO_8_MAX_REL = 0.01
FOUR_TO_8_MAX_REL = 0.005


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def final_row(factor: int) -> dict[str, float]:
    path = OUT / f"outer_{factor}.csv"
    if not path.is_file():
        fail(f"missing CSV output: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        fail(f"empty CSV output: {path}")
    out: dict[str, float] = {}
    for key, value in rows[-1].items():
        if key is None or value is None or not value.strip():
            continue
        try:
            out[key] = float(value)
        except ValueError:
            pass
    return out


def rel_change(a: float, b: float) -> float:
    # b is the larger-domain reference.  The 1 V/m floor prevents a nearly
    # zero signed probe from turning roundoff into a meaningless huge ratio.
    return abs(a - b) / max(abs(b), 1.0)


def main() -> None:
    manifest_path = OUT / "outer_domain_manifest.json"
    if not manifest_path.is_file():
        fail(f"missing outer-domain manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = {factor: final_row(factor) for factor in FACTORS}

    required = ("E_real_l2", "E_imag_l2", "E_imag_min", "E_imag_max", *PROBES)
    for factor, row in rows.items():
        missing = [key for key in required if key not in row]
        if missing:
            fail(f"outer_{factor}: missing observables {missing}")
        if abs(row["E_real_l2"]) > 1e-12:
            fail(f"outer_{factor}: E_real_l2 must remain zero, got {row['E_real_l2']}")
        if row["E_imag_l2"] <= 0.0:
            fail(f"outer_{factor}: nonzero imaginary field expected")

    baseline_vs_8: dict[str, float] = {}
    four_vs_8: dict[str, float] = {}
    for key in PROBES:
        baseline_vs_8[key] = rel_change(rows[1][key], rows[8][key])
        four_vs_8[key] = rel_change(rows[4][key], rows[8][key])

    max_baseline = max(baseline_vs_8.values())
    max_tail = max(four_vs_8.values())

    summary = {
        "issue": 202,
        "scope": "M2-F outer-domain sensitivity for zero-E_theta truncation",
        "status": "PASS" if max_baseline < BASELINE_TO_8_MAX_REL and max_tail < FOUR_TO_8_MAX_REL else "FAIL",
        "scientific_acceptance": False,
        "criteria": {
            "baseline_factor1_vs_factor8_max_relative": BASELINE_TO_8_MAX_REL,
            "factor4_vs_factor8_max_relative": FOUR_TO_8_MAX_REL,
        },
        "max_relative_changes": {
            "factor1_vs_factor8": max_baseline,
            "factor4_vs_factor8": max_tail,
        },
        "probe_relative_changes": {
            "factor1_vs_factor8": baseline_vs_8,
            "factor4_vs_factor8": four_vs_8,
        },
        "fields": {
            str(factor): {key: rows[factor][key] for key in required}
            for factor in FACTORS
        },
        "domain_manifest": manifest,
        "notes": [
            "Global E_imag_l2 is diagnostic only because the integration domain changes.",
            "Acceptance is based on signed internal probes at fixed physical coordinates.",
        ],
    }
    (OUT / "outer_domain_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    if max_tail >= FOUR_TO_8_MAX_REL:
        fail(
            "outer-domain sequence has not converged by factor 8: "
            f"max factor4->8 relative change={max_tail:.6g}"
        )
    if max_baseline >= BASELINE_TO_8_MAX_REL:
        fail(
            "committed factor-1 boundary is materially influencing the internal field: "
            f"max factor1->8 relative change={max_baseline:.6g}"
        )
    print("PASS: Issue #202 M2-F outer-domain sensitivity discriminator")


if __name__ == "__main__":
    main()
