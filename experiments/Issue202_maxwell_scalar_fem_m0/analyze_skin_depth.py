#!/usr/bin/env python3
from __future__ import annotations

import cmath
import csv
import json
import math
from pathlib import Path

CASE = Path(__file__).resolve().parent
RESULTS = CASE / "results_skin"
FREQUENCY = 13.56e6
MU0 = 1.2566370614359173e-6
EPS0 = 8.8541878128e-12
SIGMA = 100.0
RADIUS = 0.05
PROBES = (0.01, 0.02, 0.03, 0.04, 0.045)
FINE_REL_TOL = 5.0e-3


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def j1(z: complex) -> complex:
    # Entire-function power series:
    # J1(z) = sum_m (-1)^m (z/2)^(2m+1)/(m!(m+1)!)
    term = z / 2.0
    total = term
    for m in range(200):
        term *= -(z * z / 4.0) / ((m + 1) * (m + 2))
        total += term
        if abs(term) <= 1.0e-16 * max(1.0, abs(total)):
            return total
    fail(f"J1 series failed to converge for z={z}")
    raise AssertionError


def exact_field(r: float) -> complex:
    omega = 2.0 * math.pi * FREQUENCY
    kappa2 = omega * omega * MU0 * EPS0 - 1j * omega * MU0 * SIGMA
    kappa = cmath.sqrt(kappa2)
    return j1(kappa * r) / j1(kappa * RADIUS)


def final_row(level: int) -> dict[str, float]:
    path = RESULTS / f"skin_{level}.csv"
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


def key_for(component: str, r: float) -> str:
    suffix = "045" if abs(r - 0.045) < 1.0e-12 else f"{int(round(r * 100)):02d}"
    return f"E_{component}_r{suffix}"


def main() -> None:
    rows = {level: final_row(level) for level in (0, 1)}
    summary_probes: dict[str, dict[str, float]] = {}
    max_fine_rel = 0.0
    max_coarse_rel = 0.0
    improved = 0

    for r in PROBES:
        exact = exact_field(r)
        per_level: dict[int, complex] = {}
        for level, row in rows.items():
            kr = key_for("real", r)
            ki = key_for("imag", r)
            if kr not in row or ki not in row:
                fail(f"skin_{level}: missing {kr}/{ki}")
            per_level[level] = complex(row[kr], row[ki])

        err0 = abs(per_level[0] - exact) / max(abs(exact), 1.0e-14)
        err1 = abs(per_level[1] - exact) / max(abs(exact), 1.0e-14)
        max_coarse_rel = max(max_coarse_rel, err0)
        max_fine_rel = max(max_fine_rel, err1)
        if err1 <= err0 + 1.0e-12:
            improved += 1

        summary_probes[f"r={r:.3f}"] = {
            "exact_real": exact.real,
            "exact_imag": exact.imag,
            "coarse_real": per_level[0].real,
            "coarse_imag": per_level[0].imag,
            "fine_real": per_level[1].real,
            "fine_imag": per_level[1].imag,
            "coarse_relative_complex_error": err0,
            "fine_relative_complex_error": err1,
        }

    if max_fine_rel > FINE_REL_TOL:
        fail(
            f"fine-mesh analytical mismatch {max_fine_rel:.6e} exceeds "
            f"{FINE_REL_TOL:.6e}"
        )
    if improved != len(PROBES):
        fail(f"mesh refinement did not improve all probes: {improved}/{len(PROBES)}")

    omega = 2.0 * math.pi * FREQUENCY
    skin_depth = math.sqrt(2.0 / (omega * MU0 * SIGMA))
    summary = {
        "status": "PASS",
        "issue": 202,
        "scope": "M2-C conducting-cylinder scalar-RZ skin-depth analytical verification",
        "frequency_Hz": FREQUENCY,
        "sigma_S_per_m": SIGMA,
        "radius_m": RADIUS,
        "classical_skin_depth_m": skin_depth,
        "phasor": "exp(+i omega t)",
        "exact_solution": "J1(kappa*r)/J1(kappa*R), kappa^2=omega^2*mu0*eps0-i*omega*mu0*sigma",
        "fine_relative_tolerance": FINE_REL_TOL,
        "max_coarse_relative_complex_error": max_coarse_rel,
        "max_fine_relative_complex_error": max_fine_rel,
        "probes": summary_probes,
        "scientific_acceptance": False,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "skin_depth_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("PASS: Issue #202 M2-C conducting-cylinder skin-depth verification")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
