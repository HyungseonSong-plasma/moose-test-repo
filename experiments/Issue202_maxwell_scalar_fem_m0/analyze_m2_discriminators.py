#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

CASE = Path(__file__).resolve().parent
RESULTS = CASE / "results_m2"

CURRENT_CASES = {5.0: "current_5", 10.0: "current_10", 20.0: "current_20"}
SINGLE_COIL_CASES = ("coil1_only", "coil2_only", "coil3_only")
PROBES = (
    "E_imag_probe_r05",
    "E_imag_probe_r10",
    "E_imag_probe_r15",
    "E_imag_probe_r20",
)
LINEAR_KEYS = (
    "E_imag_l2",
    "E_imag_min",
    "E_imag_max",
    *PROBES,
)


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def final_row(case: str) -> dict[str, float]:
    path = RESULTS / f"{case}.csv"
    if not path.is_file():
        fail(f"missing CSV output: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        fail(f"empty CSV output: {path}")
    raw = rows[-1]
    out: dict[str, float] = {}
    for key, value in raw.items():
        if key is None or value is None or not value.strip():
            continue
        try:
            out[key] = float(value)
        except ValueError:
            pass
    return out


def require_keys(case: str, row: dict[str, float], keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in row]
    if missing:
        fail(f"{case}: missing observables {missing}")


def close(actual: float, expected: float, *, rel: float = 5e-7, abs_: float = 1e-10) -> bool:
    return math.isclose(actual, expected, rel_tol=rel, abs_tol=abs_)


def main() -> None:
    current_rows = {amps: final_row(case) for amps, case in CURRENT_CASES.items()}
    single_rows = {case: final_row(case) for case in SINGLE_COIL_CASES}

    required = ("E_real_l2", "E_imag_l2", "E_imag_min", "E_imag_max", *PROBES)
    for amps, case in CURRENT_CASES.items():
        row = current_rows[amps]
        require_keys(case, row, required)
        if abs(row["E_real_l2"]) > 1e-12:
            fail(f"{case}: vacuum real-field discriminator violated: E_real_l2={row['E_real_l2']}")
        if row["E_imag_l2"] <= 0.0:
            fail(f"{case}: nonzero imaginary field expected")

    ref = current_rows[10.0]
    if not close(ref["E_imag_l2"], 48.02961, rel=2e-6, abs_=1e-8):
        fail(f"current_10: baseline E_imag_l2 drifted: {ref['E_imag_l2']}")

    linearity: dict[str, dict[str, float]] = {}
    for amps in (5.0, 20.0):
        factor = amps / 10.0
        row = current_rows[amps]
        case_result: dict[str, float] = {}
        for key in LINEAR_KEYS:
            expected = ref[key] * factor
            actual = row[key]
            if not close(actual, expected):
                fail(
                    f"current linearity failed for {key} at {amps:g} A: "
                    f"actual={actual:.17g}, expected={expected:.17g}"
                )
            denom = max(abs(expected), 1e-30)
            case_result[key] = abs(actual - expected) / denom
        linearity[f"{amps:g}A_vs_10A"] = case_result

    for case, row in single_rows.items():
        require_keys(case, row, required)
        if abs(row["E_real_l2"]) > 1e-12:
            fail(f"{case}: E_real_l2 must remain zero, got {row['E_real_l2']}")
        if row["E_imag_l2"] <= 0.0:
            fail(f"{case}: switched-on single coil produced no field")

    superposition: dict[str, dict[str, float]] = {}
    for key in PROBES:
        expected = sum(single_rows[case][key] for case in SINGLE_COIL_CASES)
        actual = ref[key]
        if not close(actual, expected, rel=1e-6, abs_=1e-9):
            fail(
                f"coil superposition failed for {key}: "
                f"all={actual:.17g}, singles_sum={expected:.17g}"
            )
        superposition[key] = {
            "all_three": actual,
            "single_coils_sum": expected,
            "absolute_error": abs(actual - expected),
        }

    summary = {
        "status": "PASS",
        "issue": 202,
        "scope": "M2 vacuum/source current-linearity and coil-superposition discriminators",
        "current_linearity": linearity,
        "coil_superposition": superposition,
        "reference_10A": {key: ref[key] for key in required},
        "single_coil_l2": {case: row["E_imag_l2"] for case, row in single_rows.items()},
        "scientific_acceptance": False,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "m2_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("PASS: Issue #202 M2 current-linearity and coil-superposition discriminators")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
