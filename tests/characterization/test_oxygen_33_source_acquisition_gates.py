"""Traceability and scientific preflight for frozen 33-row Oxygen collision registry.

This does not download, redistribute, infer, or synthesize numerical cross sections.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "experiments/Issue395_powered_chemistry_ladder"


def load(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_gate_matrix_matches_the_33_final_collision_records():
    reg = load(DATA / "OXYGEN_FINAL_UNIFIED_COLLISION_REGISTRY_33.csv")
    gate = load(DATA / "OXYGEN_33_SOURCE_ACQUISITION_GATE_MATRIX.csv")
    assert len(reg) == len(gate) == 33
    assert [r["id"] for r in reg] == [g["key"] for g in gate]
    assert len({g["key"] for g in gate}) == 33
    for r, g in zip(reg, gate):
        assert r["scope"] == g["scope"]
        assert r["numeric"] == g["numeric_cross_section"]
        assert g["source_sha256"] == ""
        assert g["solver_rate_output"] == "NOT_RUN"
    assert sum(r["scope"] == "CHEMISTRY_ELECTRON" for r in reg) == 22
    assert sum(r["scope"] == "CHEMISTRY_HEAVY" for r in reg) == 3
    assert sum(r["scope"] == "BOLTZMANN_KINETIC_SUPPORT" for r in reg) == 7
    assert sum(r["scope"] == "BOLTZMANN_ELASTIC" for r in reg) == 1


def test_figure_matches_hpep_identity_without_accepting_chemistry_or_sigma():
    registry = {r["id"]: r for r in load(DATA / "OXYGEN_FINAL_UNIFIED_COLLISION_REGISTRY_33.csv")}
    gates = {g["key"]: g for g in load(DATA / "OXYGEN_33_SOURCE_ACQUISITION_GATE_MATRIX.csv")}
    for key, loss in (("EI-411", "4.50"), ("EI-413", "8.40"), ("EI-414", "10.00")):
        r, g = registry[key], gates[key]
        assert loss in r["energy"]
        assert g["identity_review"] == "FIGURE_HPEM_ID_MATCH_VERIFIED"
        assert r["guard"].startswith("FIGURE_HPEM_ID_VERIFIED")
        assert "UNRESOLVED" in g["physics_gate"]
        assert g["numeric_cross_section"] == "NOT_VERIFIED"
    for key, threshold in (
        ("EI-2068", "3.52"),
        ("EI-2073", "13.72"),
        ("EI-2074", "16.02"),
    ):
        r, g = registry[key], gates[key]
        assert threshold in r["energy"]
        assert "HPEM_" in r["guard"]
        assert "HOLD" in g["physics_gate"]
        assert g["numeric_cross_section"] == "NOT_VERIFIED"
    assert "~4.14eV" in registry["EI-2068"]["guard"]


def test_do_not_reintroduce_excluded_processes_or_invent_rates():
    gates = load(DATA / "OXYGEN_33_SOURCE_ACQUISITION_GATE_MATRIX.csv")
    ids = {g["key"] for g in gates}
    assert not ids.intersection({
        "KIN-R01", "KIN-E01", "KIN-E02", "KIN-EL-O2", "attachment_three_body"
    })
    assert {"KIN-M01", "KIN-EL-O", "EI-401", "EI-2058"}.issubset(ids)
    assert all(g["solver_rate_output"] == "NOT_RUN" for g in gates)


def test_drafted_hpep_request_lists_all_22_electron_chemistry_ids():
    contents = (DATA / "OXYGEN_33_ORIGINAL_SOURCE_ACQUISITION_PLAN.md").read_text(
        encoding="utf-8"
    )
    assert "REQUEST DRAFTED; NOT SENT; NUMERIC DATA NOT ACQUIRED" in contents
    assert "0–200 eV" in contents
    ids = [r["id"][3:] for r in load(DATA / "OXYGEN_FINAL_UNIFIED_COLLISION_REGISTRY_33.csv")
           if r["scope"] == "CHEMISTRY_ELECTRON"]
    section = contents.split("## Scope: 22 user-approved electron-impact Chemistry reactions", 1)[1]
    backtick = chr(96)
    listed = section.split(backtick, 2)[1].split(", ")
    assert len(listed) == 22
    assert sorted(listed) == sorted(ids)
