"""Opt-in oxygen ICP 25-channel effective-O(ex) policy, retaining physical provenance."""
import json
from pathlib import Path

from experiments.Issue395_powered_chemistry_ladder.oxygen_25_stoichiometry_contract import (
    REACTIONS, ACTIVE_REACTIONS, ACTIVE_EXCLUDED_REACTION_IDS,
    SOLVER_SPECIES_IDENTITY, active_audit, audit, stoich,
)

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "experiments" / "Issue395_powered_chemistry_ladder"


def test_25_active_channels_have_full_conservation():
    assert audit()["reaction_count"] == 25  # archival registry unchanged
    report = active_audit()
    assert report["status"] == "STOICHIOMETRY_ONLY_PASS"
    assert (report["active_reactions"], report["active_lookup_tables"],
            report["formula_reactions"], report["heavy_reactions"]) == (25, 19, 3, 3)
    assert report["excluded_reactions"] == []
    assert report["ei936_species_source_enabled"] is True
    assert report["ei936_energy_sink_enabled"] is True
    assert report["ei936_energy_loss_eV"] == 4.19
    assert "O1S" not in report["missing_transport_species"]
    ids = {r[0] for r in ACTIVE_REACTIONS}
    assert {"935", "936", "943"}.issubset(ids)
    for reaction in ACTIVE_REACTIONS:
        assert "O1S" not in stoich(reaction)
    assert stoich(next(row for row in REACTIONS if row[0]=="936")) == {"O":-1,"O1S":1}
    assert stoich(next(row for row in ACTIVE_REACTIONS if row[0]=="936")) == {"O":-1,"O1D":1}


def test_solver_O_and_Os_are_distinct_and_935_943_are_preserved():
    ledger = json.loads((ROOT / "docs/development/2026-09-07_issue17_r0_reaction_ledger.json").read_text())
    identities = {s["id"]: s.get("physical_identity", "") for s in ledger["species"]}
    assert identities["Os"] == "O(1D)"
    assert SOLVER_SPECIES_IDENTITY == {
        "O(3P)": "O", "O(1D)": "Os", "O(1S)": "Os", "O(ex)": "Os", "O2(a1Delta_g)": "O2s"
    }
    rate_by_id = {r[0]: stoich(r) for r in ACTIVE_REACTIONS}
    assert rate_by_id["935"]["O"] == -1 and rate_by_id["935"]["O1D"] == 1
    assert rate_by_id["936"]["O"] == -1 and rate_by_id["936"]["O1D"] == 1
    assert rate_by_id["943"]["O1D"] == -1 and rate_by_id["943"]["O"] == 1


def test_EI936_effective_lumping_is_recorded_without_rewriting_source_registry():
    cfg = json.loads((FOLDER / "oxygen_icp_operating_200sccm_sticking1.json").read_text())
    active = cfg["chemistry"]
    assert active["source_inventory_count"] == 25
    assert active["active_reaction_count"] == 25
    assert active["active_lookup_rate_count"] == 19
    assert active["excluded_reactions"] == []
    assert active["disabled_reaction_progress"] == []
    assert active["disabled_species_and_energy_sources"] == []
    assert ACTIVE_EXCLUDED_REACTION_IDS == set()
    assert active["ei936"]["effective_product_variable"] == "w_Os"
    assert active["ei936"]["electron_energy_loss_eV"] == 4.19
    assert active["ei936"]["independent_from_ei935"] is True
    assert cfg["rf_targets_w"] == [400, 1000]
    assert cfg["inlet"]["Q_sccm"] == 200
    assert cfg["wall"]["research_uniform_sticking"] is True
