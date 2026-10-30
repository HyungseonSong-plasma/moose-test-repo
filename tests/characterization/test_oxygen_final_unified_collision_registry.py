"""Structure/identity checks for the user-approved 36-row oxygen collision scope.
No actual numerical cross sections are distributed by this fixture.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments/Issue395_powered_chemistry_ladder/OXYGEN_FINAL_UNIFIED_COLLISION_REGISTRY_36.csv"
PHELPS = ROOT / "experiments/Issue395_powered_chemistry_ladder/OXYGEN_BOLTZMANN_COLLISION_INVENTORY.csv"


def load(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_scope_and_unique_ids():
    rows = load(SOURCE)
    assert len(rows) == 36
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    assert sum(r["scope"] == "CHEMISTRY_ELECTRON" for r in rows) == 22
    assert sum(r["scope"] == "CHEMISTRY_HEAVY" for r in rows) == 3
    assert sum(r["scope"] == "BOLTZMANN_KINETIC_SUPPORT" for r in rows) == 10
    assert sum(r["scope"] == "BOLTZMANN_ELASTIC" for r in rows) == 1
    assert "KIN-EL-O" in ids
    assert "KIN-M01" in ids
    assert "KIN-EL-O2" not in ids


def test_selected_o2_effective_qm_and_distinct_atomic_o_elastic():
    records = {v["id"]: v for v in load(SOURCE)}
    assert "KIN-EL-O2" not in records
    assert "KIN-M01" in records
    assert records["KIN-EL-O"]["process"] == "e + O(3P) -> e + O(3P)"
    assert "Itikawa" in records["KIN-EL-O"]["source"]
    assert records["KIN-EL-O"]["numeric"] == "NOT_VERIFIED"
    assert "EFFECTIVE" in records["KIN-M01"]["role"]
    assert "SELECTED_O2_EFFECTIVE_QM" in records["KIN-M01"]["guard"]
    assert "not pure elastic recoil" in records["KIN-M01"]["guard"]
    assert "do not add O2 separate elastic scattering" in records["KIN-M01"]["guard"]
    assert "recoil" in records["KIN-M01"]["guard"]
    assert records["KIN-M01"]["numeric"] == "NOT_VERIFIED"

def test_no_unregistered_three_body_attachment():
    rows = load(SOURCE)
    phelps = load(PHELPS)
    assert len(phelps) == 17
    assert not any("three_body" in r["source_key"] for r in phelps)
    assert not any("three_body" in r["id"] or "three-body attachment" in r["process"].lower() for r in rows)
    assert "EI-401" in {r["id"] for r in rows}
    assert "EI-2058" in {r["id"] for r in rows}
    assert "O2-" not in " ".join(r["process"] for r in rows if r["id"].startswith("KIN-"))


def test_existing_chemistry_and_kinetic_support_are_one_to_one():
    final = {r["id"]: r for r in load(SOURCE)}
    source = load(PHELPS)
    for record in source:
        rid = ("EI-" + record["table_id"] if record["inventory_role"] == "CHEMISTRY_MATCHED" else record["table_id"])
        assert rid in final
        if record["inventory_role"] == "CHEMISTRY_MATCHED":
            assert final[rid]["scope"] == "CHEMISTRY_ELECTRON"
        else:
            assert final[rid]["scope"] == "BOLTZMANN_KINETIC_SUPPORT"
        assert final[rid]["numeric"] == "NOT_VERIFIED"
