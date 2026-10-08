#!/usr/bin/env python3
"""Compare MOOSE M2-G chamber probes against the independent FEM reference."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

PROBES = [
    "p1", "p2", "p3", "p4", "p5", "p6",
    "q1", "q2", "q3", "q4",
    "v1", "v2", "v3", "v4",
]

COMPLEX_REL_TOL = 5.0e-3
MAG_REL_TOL = 5.0e-3
PHASE_TOL_DEG = 0.5


class AnalysisError(RuntimeError):
    pass


def load_final_csv(path: Path) -> dict[str, float]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise AnalysisError(f"no rows in {path}")
    return {key: float(value) for key, value in rows[-1].items() if key and value not in (None, "")}


def phase_delta_deg(a: complex, b: complex) -> float:
    da = math.degrees(math.atan2(a.imag, a.real))
    db = math.degrees(math.atan2(b.imag, b.real))
    return abs((da - db + 180.0) % 360.0 - 180.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moose-csv", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    moose = load_final_csv(args.moose_csv)
    reference = json.loads(args.reference.read_text())
    results: dict[str, dict[str, float | str]] = {}

    max_complex = 0.0
    max_mag = 0.0
    max_phase = 0.0
    nonzero_real = 0
    nonzero_imag = 0

    for name in PROBES:
        rk = f"E_real_{name}"
        ik = f"E_imag_{name}"
        if rk not in moose or ik not in moose:
            raise AnalysisError(f"missing MOOSE probe columns for {name}")
        try:
            ref_data = reference["probes"][name]
        except KeyError as exc:
            raise AnalysisError(f"missing reference probe {name}") from exc

        m = complex(moose[rk], moose[ik])
        r = complex(float(ref_data["real"]), float(ref_data["imag"]))
        if abs(m.real) > 1e-10:
            nonzero_real += 1
        if abs(m.imag) > 1e-10:
            nonzero_imag += 1

        complex_rel = abs(m - r) / max(abs(r), 1e-12)
        mag_rel = abs(abs(m) - abs(r)) / max(abs(r), 1e-12)
        phase = phase_delta_deg(m, r) if abs(r) > 1e-10 else 0.0
        max_complex = max(max_complex, complex_rel)
        max_mag = max(max_mag, mag_rel)
        max_phase = max(max_phase, phase)
        results[name] = {
            "block": str(ref_data["block"]),
            "moose_real": m.real,
            "moose_imag": m.imag,
            "reference_real": r.real,
            "reference_imag": r.imag,
            "complex_relative_error": complex_rel,
            "magnitude_relative_error": mag_rel,
            "phase_error_deg": phase,
        }

    failures: list[str] = []
    if max_complex > COMPLEX_REL_TOL:
        failures.append(f"max complex relative error {max_complex:.6e} > {COMPLEX_REL_TOL:.6e}")
    if max_mag > MAG_REL_TOL:
        failures.append(f"max magnitude relative error {max_mag:.6e} > {MAG_REL_TOL:.6e}")
    if max_phase > PHASE_TOL_DEG:
        failures.append(f"max phase error {max_phase:.6e} deg > {PHASE_TOL_DEG:.6e} deg")
    if nonzero_real < len(PROBES) // 2:
        failures.append("prescribed complex conductivity did not activate the real field at enough probes")
    if nonzero_imag < len(PROBES) // 2:
        failures.append("imaginary field is unexpectedly zero at too many probes")

    report = {
        "issue": 202,
        "scope": "M2-G MOOSE vs independent complex scalar-RZ FEM prescribed-material chamber equivalence",
        "status": "FAIL" if failures else "PASS",
        "scientific_acceptance": False,
        "comparison": "same frozen qvt.msh and coefficients, independently assembled complex FEM reference",
        "tolerances": {
            "complex_relative": COMPLEX_REL_TOL,
            "magnitude_relative": MAG_REL_TOL,
            "phase_deg": PHASE_TOL_DEG,
        },
        "max_complex_relative_error": max_complex,
        "max_magnitude_relative_error": max_mag,
        "max_phase_error_deg": max_phase,
        "nonzero_real_probe_count": nonzero_real,
        "nonzero_imag_probe_count": nonzero_imag,
        "probes": results,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if failures:
        print("FAIL: Issue #202 M2-G chamber cross-solver equivalence")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    print("PASS: Issue #202 M2-G chamber cross-solver equivalence")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
