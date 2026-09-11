#!/usr/bin/env python3
"""Static recovery guard for the S5-R EI16 O2-ionization production-rate owner.

This guard validates only recovered source identity and owner binding. It does not
claim representative assembly, physics-opt --check-input, runtime PASS, or Stage-5
acceptance.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECOVERY = ROOT / "docs/development/2026-09-11_issue192_s5r_ei16_ionization_recovery.json"
TABLE = ROOT / "physics_app/data/electron_impact/o2_ionization.txt"
EI16 = ROOT / "docs/development/2026-09-10_issue26_e8_ei16_energy_contract.json"
COMPANIONS = (
    ROOT / "physics_app/data/electron_impact/o_ionization.txt",
    ROOT / "physics_app/data/electron_impact/o2_elastic.txt",
)


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise AssertionError(f"missing required contract: {path.relative_to(ROOT)}")
    return json.loads(path.read_text())


def _read_two_column_table(path: Path) -> list[tuple[float, float]]:
    if not path.is_file():
        raise AssertionError(f"missing required table: {path.relative_to(ROOT)}")
    rows = []
    for line_no, raw in enumerate(path.read_text().splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        fields = stripped.split()
        if len(fields) != 2:
            raise AssertionError(f"{path.relative_to(ROOT)}:{line_no}: expected two columns")
        rows.append((float(fields[0]), float(fields[1])))
    return rows


def check() -> None:
    recovery = _load_json(RECOVERY)
    ei16 = _load_json(EI16)

    if recovery.get("schema_version") != 1:
        raise AssertionError("unexpected EI16 recovery schema")
    if recovery.get("controller_issue") != 176 or recovery.get("child_issue") != 192:
        raise AssertionError("EI16 recovery controller/child identity changed")
    if recovery.get("channel") != "EI16_O2_IONIZATION":
        raise AssertionError("EI16 recovery channel identity changed")
    if recovery.get("status") != "PRODUCTION_RATE_OWNER_RECOVERED":
        raise AssertionError("EI16 production rate owner is not recovered")

    provenance = recovery.get("provenance", {})
    if provenance.get("source_identity") != "user_supplied:o2_ionization":
        raise AssertionError("EI16 source identity changed")
    if provenance.get("canonical_path") != "physics_app/data/electron_impact/o2_ionization.txt":
        raise AssertionError("EI16 canonical table path changed")

    raw = TABLE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != provenance.get("sha256"):
        raise AssertionError("EI16 table SHA-256 does not match frozen recovery provenance")

    lookup = recovery.get("lookup_contract", {})
    if lookup.get("coordinate") != "mean_en_solved":
        raise AssertionError("EI16 lookup coordinate is not solved mean energy")
    if lookup.get("coordinate_unit") != "eV":
        raise AssertionError("EI16 lookup coordinate unit changed")
    if lookup.get("value_unit") != "m^3/(mol s)":
        raise AssertionError("EI16 lookup rate unit changed")
    if lookup.get("rows") != 100:
        raise AssertionError("EI16 lookup row count contract changed")
    if lookup.get("domain_eV") != [1.40991, 22.1378]:
        raise AssertionError("EI16 lookup domain changed")
    if lookup.get("bounds_policy") != "error":
        raise AssertionError("EI16 lookup must remain strict")

    rows = _read_two_column_table(TABLE)
    if len(rows) != lookup["rows"]:
        raise AssertionError("EI16 table row count does not match recovery contract")
    if rows[0][0] != lookup["domain_eV"][0] or rows[-1][0] != lookup["domain_eV"][1]:
        raise AssertionError("EI16 table domain does not match recovery contract")
    for (x0, _), (x1, _) in zip(rows, rows[1:]):
        if not x1 > x0:
            raise AssertionError("EI16 mean-energy grid must be strictly increasing")

    row_map = dict(rows)
    for x_text, expected in lookup.get("anchors_m3_per_mol_s", {}).items():
        x = float(x_text)
        if x not in row_map or row_map[x] != expected:
            raise AssertionError(f"EI16 table anchor mismatch at {x_text} eV")

    coordinate_grid = [x for x, _ in rows]
    for companion in COMPANIONS:
        companion_rows = _read_two_column_table(companion)
        if [x for x, _ in companion_rows] != coordinate_grid:
            raise AssertionError(
                f"EI16 mean-energy coordinate grid differs from companion {companion.relative_to(ROOT)}"
            )

    owner = recovery.get("progress_owner", {})
    if owner.get("type") != "PhysicsElectronImpactIonizationMaterial":
        raise AssertionError("EI16 progress owner type changed")
    if owner.get("rate_table_file") != "physics_app/data/electron_impact/o2_ionization.txt":
        raise AssertionError("EI16 progress owner table binding changed")
    if owner.get("mean_energy") != "mean_en_solved":
        raise AssertionError("EI16 progress owner mean-energy binding changed")
    if owner.get("reaction_progress") != "R_ion_O2":
        raise AssertionError("EI16 canonical progress identity changed")

    projection = recovery.get("projection_contract", {})
    if projection.get("energy_loss_eV") != 12.06:
        raise AssertionError("EI16 energy-loss identity changed")
    if projection.get("duplicate_kinetic_reevaluation") != "FORBIDDEN":
        raise AssertionError("EI16 duplicate kinetic reevaluation guard changed")

    synthetic = recovery.get("synthetic_fixture_boundary", {})
    if synthetic.get("production_use") != "FORBIDDEN":
        raise AssertionError("historical EI16 synthetic discriminator was made production-eligible")
    fixture_note = ei16.get("lookup_policy", {}).get("controlled_fixture_note", "")
    if "synthetic" not in fixture_note.lower() or "not physical rate provenance" not in fixture_note.lower():
        raise AssertionError("EI16 Stage-4 synthetic-fixture boundary changed")

    print("S5R_EI16_PRODUCTION_RATE_OWNER_RECOVERY_PASS")
    print(f"table_sha256={provenance['sha256']}")
    print("rows=100")
    print("domain_eV=1.40991..22.1378")
    print("progress_owner=R_ion_O2")
    print("representative_assembly=NOT_YET_ESTABLISHED")


if __name__ == "__main__":
    check()
