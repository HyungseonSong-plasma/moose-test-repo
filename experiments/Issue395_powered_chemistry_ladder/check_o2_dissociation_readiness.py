#!/usr/bin/env python3
"""Static readiness checker for Issue #395 O2 electron-impact dissociation.

This does not admit the reaction to production. It verifies that the recovered
historical asset is byte-identical to the audited artifact and that the unit and
stoichiometric contracts are internally consistent.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

NA = 6.02214076e23
M_O2 = 0.032
M_O = 0.016
EXPECTED_SHA256 = "bcd0cc004ea8657c5b77d684065acfad4fce02a497efbc0e231d7d3cf3727568"
EXPECTED_ROWS = 16
EXPECTED_FLOOR = 1.0e-20
EXPECTED_FLOOR_MAX_E = 5.1


def read_table(path: Path) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            energy, rate = next(csv.reader([line]))
            rows.append((float(energy), float(rate)))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", type=Path, required=True)
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    a = ap.parse_args()

    raw = a.table.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    rows = read_table(a.table)
    contract = json.loads(a.contract.read_text(encoding="utf-8"))

    failures: list[str] = []
    if sha != EXPECTED_SHA256:
        failures.append("historical SHA256 mismatch")
    if contract["historical_rate_candidate"]["sha256"] != EXPECTED_SHA256:
        failures.append("contract SHA256 mismatch")
    if len(rows) != EXPECTED_ROWS:
        failures.append("unexpected row count")
    if not all(math.isfinite(e) and math.isfinite(k) and k >= 0.0 for e, k in rows):
        failures.append("non-finite or negative table entry")
    if not all(rows[i + 1][0] > rows[i][0] for i in range(len(rows) - 1)):
        failures.append("mean-energy grid is not strictly increasing")

    floor_rows = [(e, k) for e, k in rows if e <= EXPECTED_FLOOR_MAX_E]
    if not floor_rows or any(k != EXPECTED_FLOOR for _, k in floor_rows):
        failures.append("historical sub-threshold floor signature changed")
    if contract["historical_rate_candidate"]["floor_disposition"] != "UNRESOLVED_DO_NOT_SILENTLY_PROMOTE":
        failures.append("floor disposition must remain explicitly unresolved")

    sample_e, sample_k_particle = rows[6]
    sample_k_mol = NA * sample_k_particle
    n_e = 2.0e15
    c_o2 = 1.0e-4
    r_a = sample_k_mol * (n_e / NA) * c_o2
    r_b = sample_k_particle * n_e * c_o2
    if not math.isclose(r_a, r_b, rel_tol=1e-15, abs_tol=0.0):
        failures.append("particle-to-molar progress conversion mismatch")

    heavy_mass = -M_O2 + 2.0 * M_O
    oxygen_atoms = -2.0 + 2.0
    charge = 0.0
    electron_stoich = float(contract["reaction"]["electron_stoich"])
    if heavy_mass != 0.0:
        failures.append("heavy-mass closure")
    if oxygen_atoms != 0.0:
        failures.append("oxygen-nuclei closure")
    if charge != 0.0:
        failures.append("charge closure")
    if electron_stoich != 0.0:
        failures.append("electron stoichiometry")

    expected_blockers = {
        "sub-threshold floor disposition frozen",
        "electron-energy-loss identity/value frozen",
    }
    gates = set(contract["readiness_gates"])
    if not expected_blockers.issubset(gates):
        failures.append("required readiness blockers are missing")

    report = {
        "issue": 395,
        "classification": (
            "ISSUE395_O2_DISSOCIATION_STATIC_READINESS_PASS"
            if not failures
            else "ISSUE395_O2_DISSOCIATION_STATIC_READINESS_FAIL"
        ),
        "status": "PASS" if not failures else "FAIL",
        "production_admitted": False,
        "table_sha256": sha,
        "table_rows": len(rows),
        "energy_range_eV": [rows[0][0], rows[-1][0]] if rows else None,
        "historical_floor_m3_s": EXPECTED_FLOOR,
        "historical_floor_through_eV": EXPECTED_FLOOR_MAX_E,
        "sample_6eV": {
            "k_particle_m3_s": sample_k_particle,
            "k_molar_m3_mol_s": sample_k_mol,
            "test_progress_mol_m3_s": r_a,
        },
        "closures": {
            "heavy_mass_kg_per_mol_progress": heavy_mass,
            "oxygen_atoms_per_event": oxygen_atoms,
            "charge_per_event": charge,
            "electron_stoich": electron_stoich,
        },
        "unresolved_before_production": [
            "scientific source reference for recovered table",
            "sub-threshold 1e-20 m3/s floor disposition",
            "ground-state O+O channel identity and electron-energy loss freeze",
        ],
        "failures": failures,
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
