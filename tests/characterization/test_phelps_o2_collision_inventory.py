"""Guard the selected Phelps O2 inventory against chemistry scope changes.

No third-party numerical cross sections are contained in this test.
"""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[2]
EXTRACTOR = BASE / "experiments/Issue395_powered_chemistry_ladder/collect_phelps_o2_core_set.py"
INVENTORY = BASE / "experiments/Issue395_powered_chemistry_ladder/OXYGEN_BOLTZMANN_COLLISION_INVENTORY.csv"


def _channels():
    s = importlib.util.spec_from_file_location("phelps_o2_core_inventory_contract", EXTRACTOR)
    assert s and s.loader
    m = importlib.util.module_from_spec(s)
    sys.modules[s.name] = m
    s.loader.exec_module(m)
    return m


def test_inventory_is_exact_extractor_selection_and_not_new_chemistry():
    m = _channels()
    with INVENTORY.open(encoding="utf-8", newline="") as inp:
        rows = list(csv.DictReader(inp))
    expected_names = {ch.name for ch in m.CHANNELS}
    actual_names = [r["source_key"] for r in rows]
    assert len(rows) == 17
    assert len(set(actual_names)) == 17
    assert set(actual_names) == expected_names
    assert "attachment_three_body" not in expected_names
    assert "attachment_three_body" not in actual_names
    assert len([r for r in rows if r["inventory_role"] == "KINETIC_SUPPORT"]) == 10
    assert len([r for r in rows if r["inventory_role"] == "CHEMISTRY_MATCHED"]) == 7
    assert {r["existing_chemistry_id"] for r in rows if r["inventory_role"] == "CHEMISTRY_MATCHED"} == {
        "401", "407", "411", "412", "413", "414", "415"
    }
    for r in rows:
        assert r["source_numeric_status"] == "NUMERIC_CROSS_SECTION_NOT_VERIFIED"
        assert r["source_uri"] == m.SOURCE
        assert int(r["expected_phelps_points"]) == next(ch.count for ch in m.CHANNELS if ch.name == r["source_key"])
        assert r["selection_policy"]
        assert r["scientific_gate"]
        if r["inventory_role"] == "KINETIC_SUPPORT":
            assert r["table_id"].startswith("KIN-")
            assert r["existing_chemistry_id"] == ""
            assert r["selection_policy"] != "CHEMISTRY_ALLOWED"
        else:
            assert r["table_id"] == r["existing_chemistry_id"]
    assert all("O2-" not in r["process"] for r in rows if r["inventory_role"] == "KINETIC_SUPPORT")


def test_optional_channels_are_held_and_not_mapped_to_hpep_2073():
    with INVENTORY.open(encoding="utf-8", newline="") as inp:
        rows = {r["source_key"]: r for r in csv.DictReader(inp)}
    for key in ("b1sigma", "line_130nm"):
        assert rows[key]["selection_policy"].startswith("OPTIONAL_HOLD")
        assert not rows[key]["existing_chemistry_id"]
    assert "2073" in rows["line_130nm"]["scientific_gate"]
    assert rows["loss_4p5"]["selection_policy"] == "SOURCE_MAPPING_HOLD"
    assert rows["loss_6"]["selection_policy"] == "SOURCE_MAPPING_HOLD"
