"""Regression for research-only full 25 channel conservation ledger."""
from experiments.Issue395_powered_chemistry_ladder.oxygen_25_stoichiometry_contract import (
    REACTIONS, KNOWN_SCIENCE_HOLDS, audit, stoich
)

def test_25_chemistry_conservation_and_owners():
    report=audit()
    assert report["conservation"]=="PASS"
    assert (report["lookup_count"],report["formula_count"],report["heavy_count"])==(20,2,3)
    assert report["powered_ICP_run"]=="NOT_RUN"
    assert set(report["missing_transport_species"])=={"O2star","O1S"}
    assert "2073" in KNOWN_SCIENCE_HOLDS

def test_ionization_partial_never_count_total_twice():
    s={r[0]:stoich(r) for r in REACTIONS}
    for rid in ("415","417","2072","2074","941","944"):
        assert s[rid]["e"]==1
    assert s["415"]["O2p"]==1 and s["417"]["Op"]==1
    assert s["2072"]["O2p"]==1 and s["2074"]["Op"]==1

def test_attachment_and_recombination_charge():
    s={r[0]:stoich(r) for r in REACTIONS}
    assert s["401"]["e"]==-1 and s["401"]["Om"]==1
    assert s["2058"]["e"]==-1
    assert s["2259"]["e"]==-1 and s["2259"]["O2p"]==-1
    assert s["2738"]["e"]==1 and s["2738"]["Om"]==-1
