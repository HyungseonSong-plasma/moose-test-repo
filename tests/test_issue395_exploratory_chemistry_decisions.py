"""Exploratory 25-channel O(ex) user decisions without changing canonical HPEM registry."""
import json
from pathlib import Path

from experiments.Issue395_powered_chemistry_ladder.oxygen_25_stoichiometry_contract import (
    ACTIVE_REACTIONS, REACTIONS, active_audit, stoich
)

FOLDER = Path(__file__).resolve().parents[1] / "experiments/Issue395_powered_chemistry_ladder"


def test_reduced_chosen_oxygen_product_channels():
    active = {row[0]: stoich(row) for row in ACTIVE_REACTIONS}
    assert active["411"] == {"O2": -1, "O": 2}
    for rid in ("2068", "2073"):
        assert active[rid] == {"O2a": -1, "O": 2}
    assert active["407"] == {"O2": -1, "O2a": 1}
    assert len(ACTIVE_REACTIONS) == 25
    assert len(REACTIONS) == 25
    assert active["936"] == {"O":-1, "O1D":1}
    assert next(row for row in REACTIONS if row[0]=="936")[2] == "e O1S"


def test_heavy_3_and_old_zhao_double_count_prevention():
    cfg = json.loads((FOLDER / "oxygen_icp_operating_200sccm_sticking1.json").read_text())
    decisions = cfg["chemistry"]
    assert decisions["effective_dissociation_choices"]["reaction_ids"] == ["411", "2068", "2073"]
    assert decisions["dissociation_double_count_guard"]["legacy_Zhao_DISS_G"].startswith("disable")
    heavy = decisions["heavy_research_activation"]
    assert heavy["active_reaction_ids"] == ["H23", "H24", "H25"]
    assert heavy["all_three_enabled_in_selected_research_network"] is True
    assert "2e-17" in heavy["H25_temperature_model"]
    assert decisions["ei2259"]["adopted_provisional_rate_basis"] == "thermal_formula_not_EEDF_lookup"
    assert decisions["ei2738"]["rate_mode"] == "formula"
    assert "2.0e-13" in decisions["ei2738"]["formula"]
    assert decisions["ei412"]["rate_mode"] == "lookup"
    assert decisions["ei2259"]["rate_mode"] == "formula"
    assert set(active_audit()["user_selected_O3P_dissociation_reaction_ids"]) == {"411", "2068", "2073"}
    assert active_audit()["legacy_Zhao_dissociation_parallel_activation_allowed"] is False
