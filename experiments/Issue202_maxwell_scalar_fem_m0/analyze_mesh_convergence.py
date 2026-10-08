#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path

CASE = Path(__file__).resolve().parent
RESULTS = CASE / "results_mesh"
LEVELS = (0, 1, 2)
PROBES = (
    "E_imag_probe_r05",
    "E_imag_probe_r10",
    "E_imag_probe_r15",
    "E_imag_probe_r20",
)
PRIMARY = ("E_imag_l2", *PROBES)
DIAGNOSTIC = ("E_imag_min", "E_imag_max")
FINE_MEDIUM_REL_TOL = 1.0e-2


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def final_row(level: int) -> dict[str, float]:
    path = RESULTS / f"mesh_{level}.csv"
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


def mesh_counts(level: int) -> dict[str, int]:
    path = RESULTS / f"mesh_{level}.log"
    if not path.is_file():
        fail(f"missing runtime log: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "nodes": r"^\s*Nodes:\s+(\d+)\s*$",
        "elements": r"^\s*Elems:\s+(\d+)\s*$",
        "dofs": r"^\s*Num DOFs:\s+(\d+)\s*$",
    }
    out: dict[str, int] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.MULTILINE)
        if not match:
            fail(f"mesh_{level}: could not parse {key} from {path}")
        out[key] = int(match.group(1))
    return out


def rel_change(a: float, b: float) -> float:
    return abs(b - a) / max(abs(b), abs(a), 1.0e-30)


def observed_order(q0: float, q1: float, q2: float) -> float | None:
    d01 = abs(q1 - q0)
    d12 = abs(q2 - q1)
    scale = max(abs(q0), abs(q1), abs(q2), 1.0)
    floor = 1.0e-14 * scale
    if d01 <= floor or d12 <= floor:
        return None
    return math.log(d01 / d12, 2.0)


def main() -> None:
    rows = {level: final_row(level) for level in LEVELS}
    counts = {level: mesh_counts(level) for level in LEVELS}
    required = ("E_real_l2", *PRIMARY, *DIAGNOSTIC)

    for level, row in rows.items():
        missing = [key for key in required if key not in row]
        if missing:
            fail(f"mesh_{level}: missing observables {missing}")
        if abs(row["E_real_l2"]) > 1.0e-12:
            fail(f"mesh_{level}: E_real_l2 must remain zero, got {row['E_real_l2']}")
        if row["E_imag_l2"] <= 0.0:
            fail(f"mesh_{level}: nonzero imaginary field expected")

    for previous, current in zip(LEVELS, LEVELS[1:]):
        if counts[current]["elements"] <= counts[previous]["elements"]:
            fail(
                f"mesh element count did not increase from level {previous} to {current}: "
                f"{counts[previous]['elements']} -> {counts[current]['elements']}"
            )
        if counts[current]["dofs"] <= counts[previous]["dofs"]:
            fail(
                f"DOF count did not increase from level {previous} to {current}: "
                f"{counts[previous]['dofs']} -> {counts[current]['dofs']}"
            )

    convergence: dict[str, dict[str, float | None]] = {}
    for key in (*PRIMARY, *DIAGNOSTIC):
        q0, q1, q2 = (rows[level][key] for level in LEVELS)
        convergence[key] = {
            "level0": q0,
            "level1": q1,
            "level2": q2,
            "relative_change_0_to_1": rel_change(q0, q1),
            "relative_change_1_to_2": rel_change(q1, q2),
            "observed_order": observed_order(q0, q1, q2),
        }

    failed_primary = {
        key: convergence[key]["relative_change_1_to_2"]
        for key in PRIMARY
        if float(convergence[key]["relative_change_1_to_2"] or 0.0) > FINE_MEDIUM_REL_TOL
    }
    if failed_primary:
        fail(
            "fine/medium mesh change exceeds 1% for primary observables: "
            + json.dumps(failed_primary, sort_keys=True)
        )

    l2_coarse_medium = float(convergence["E_imag_l2"]["relative_change_0_to_1"] or 0.0)
    l2_medium_fine = float(convergence["E_imag_l2"]["relative_change_1_to_2"] or 0.0)
    if l2_medium_fine > l2_coarse_medium + 1.0e-12:
        fail(
            "global L2 convergence trend did not improve: "
            f"coarse->medium={l2_coarse_medium:.6e}, medium->fine={l2_medium_fine:.6e}"
        )

    summary = {
        "status": "PASS",
        "issue": 202,
        "scope": "M2 vacuum/source global mesh-convergence discriminator",
        "mesh_levels": counts,
        "fine_medium_relative_tolerance": FINE_MEDIUM_REL_TOL,
        "primary_observables": list(PRIMARY),
        "diagnostic_only_observables": list(DIAGNOSTIC),
        "convergence": convergence,
        "scientific_acceptance": False,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "mesh_convergence_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("PASS: Issue #202 M2 global mesh-convergence discriminator")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
