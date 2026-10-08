#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

CASE = Path(__file__).resolve().parent
RESULTS = CASE / "results_dielectric"
MU0 = 1.2566370614359173e-6
EPS0 = 8.8541878128e-12
FREQUENCY = 1.0e9
EPS1 = 1.0
EPS2 = 4.0
X_INTERFACE = 0.025
LENGTH = 0.05
PROBES = (0.01, 0.02, 0.025, 0.03, 0.04, 0.045)
FINE_REL_TOL = 1.0e-3


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def transfer(k: float, dx: float) -> tuple[tuple[float, float], tuple[float, float]]:
    c = math.cos(k * dx)
    s = math.sin(k * dx)
    return ((c, s / k), (-k * s, c))


def matmul(a, b):
    return tuple(
        tuple(sum(a[i][m] * b[m][j] for m in range(2)) for j in range(2))
        for i in range(2)
    )


def apply(m, state):
    return (
        m[0][0] * state[0] + m[0][1] * state[1],
        m[1][0] * state[0] + m[1][1] * state[1],
    )


omega = 2.0 * math.pi * FREQUENCY
K1 = omega * math.sqrt(MU0 * EPS0 * EPS1)
K2 = omega * math.sqrt(MU0 * EPS0 * EPS2)
M1 = transfer(K1, X_INTERFACE)
M2 = transfer(K2, LENGTH - X_INTERFACE)
MT = matmul(M2, M1)
INITIAL_SLOPE = 1.0 / MT[0][1]
INTERFACE_STATE = apply(M1, (0.0, INITIAL_SLOPE))


def exact_field(x: float) -> float:
    if x <= X_INTERFACE + 1.0e-15:
        return apply(transfer(K1, x), (0.0, INITIAL_SLOPE))[0]
    return apply(transfer(K2, x - X_INTERFACE), INTERFACE_STATE)[0]


def probe_key(x: float) -> str:
    if abs(x - X_INTERFACE) < 1.0e-12:
        return "E_interface"
    if abs(x - 0.045) < 1.0e-12:
        return "E_x045"
    return f"E_x{int(round(x * 100)):02d}"


def final_row(level: int) -> dict[str, float]:
    path = RESULTS / f"dielectric_{level}.csv"
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


def main() -> None:
    rows = {level: final_row(level) for level in (0, 1)}
    probes: dict[str, dict[str, float]] = {}
    max_coarse = 0.0
    max_fine = 0.0
    improved = 0

    for x in PROBES:
        key = probe_key(x)
        exact = exact_field(x)
        if key not in rows[0] or key not in rows[1]:
            fail(f"missing observable {key}")
        coarse = rows[0][key]
        fine = rows[1][key]
        scale = max(abs(exact), 1.0e-14)
        err0 = abs(coarse - exact) / scale
        err1 = abs(fine - exact) / scale
        max_coarse = max(max_coarse, err0)
        max_fine = max(max_fine, err1)
        if err1 <= err0 + 1.0e-12:
            improved += 1
        probes[f"x={x:.3f}"] = {
            "exact": exact,
            "coarse": coarse,
            "fine": fine,
            "coarse_relative_error": err0,
            "fine_relative_error": err1,
        }

    if max_fine > FINE_REL_TOL:
        fail(f"fine analytical mismatch {max_fine:.6e} exceeds {FINE_REL_TOL:.6e}")
    if improved != len(PROBES):
        fail(f"mesh refinement did not improve all probes: {improved}/{len(PROBES)}")

    # Independent exact interface continuity record.  For constant mu, the
    # scalar weak form requires continuity of E and dE/dx across this interface.
    u_int, du_int = INTERFACE_STATE
    right_start = apply(transfer(K2, 0.0), INTERFACE_STATE)
    continuity_u = abs(right_start[0] - u_int)
    continuity_du = abs(right_start[1] - du_int)

    summary = {
        "status": "PASS",
        "issue": 202,
        "scope": "M2-D dielectric/material-interface coefficient and continuity verification",
        "frequency_Hz": FREQUENCY,
        "epsilon_r_left": EPS1,
        "epsilon_r_right": EPS2,
        "interface_m": X_INTERFACE,
        "fine_relative_tolerance": FINE_REL_TOL,
        "max_coarse_relative_error": max_coarse,
        "max_fine_relative_error": max_fine,
        "exact_interface_E_continuity_error": continuity_u,
        "exact_interface_dE_dx_continuity_error": continuity_du,
        "probes": probes,
        "scientific_acceptance": False,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "dielectric_interface_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("PASS: Issue #202 M2-D dielectric/material-interface verification")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
