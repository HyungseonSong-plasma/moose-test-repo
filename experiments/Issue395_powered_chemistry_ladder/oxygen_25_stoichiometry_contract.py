"""Audited 25-channel oxygen ICP stoichiometry contract. NOT a powered ICP solver."""
from __future__ import annotations

SPECIES={
 "e":(0,-1), "O2":(2,0), "O2a":(2,0), "O2star":(2,0),
 "O":(1,0), "O1D":(1,0), "O1S":(1,0), "O2p":(2,1),
 "Op":(1,1), "Om":(1,-1)
}
# ID, reactants, products, rate owner type
REACTIONS=[
 ("401","e O2","Om O","lookup"),
 ("407","e O2","e O2a","lookup"),
 ("411","e O2","e O O","lookup"),
 ("412","e O2","e O O","lookup"),
 ("413","e O2","e O2star","lookup"),
 ("414","e O2","e O2star","lookup"),
 ("415","e O2","e e O2p","lookup"),
 ("417","e O2","e e Op O","lookup"),
 ("2058","e O2a","Om O","lookup"),
 ("2067","e O2a","e O2","lookup"),
 ("2068","e O2a","e O O","lookup"),
 ("2069","e O2a","e O O","lookup"),
 ("2072","e O2a","e e O2p","lookup"),
 ("2073","e O2a","e O O","lookup"),
 ("2074","e O2a","e e Op O","lookup"),
 ("935","e O","e O1D","lookup"),
 ("936","e O","e O1S","lookup"),
 ("941","e O","e e Op","lookup"),
 ("943","e O1D","e O","lookup"),
 ("944","e O1D","e e Op","lookup"),
 ("2259","e O2p","O O","formula"),
 ("2738","e Om","e e O","formula"),
 ("H23","Op Om","O O","heavy"),
 ("H24","Om O2p","O2 O","heavy"),
 ("H25","Op O2","O O2p","heavy"),
]
KNOWN_SCIENCE_HOLDS={
 "411":"4.5 eV threshold less than O2(X) -> 2 O(3P) dissociation energy",
 "413":"untracked O2star product; effective excitation identity unresolved",
 "414":"untracked O2star product; effective excitation identity unresolved",
 "2068":"threshold mismatch; user requested tag-only",
 "2073":"130 nm channel products unresolved",
 "936":"O(1S) 4.19 eV channel mapped into effective O(ex)/Os; state-resolved O(1S) kinetics not solved",
 "2259":"formula validated only for equivalent Te=1-7 eV",
 "2738":"formula validated only for equivalent Te=1-7 eV",
 "H25":"reference temperature convention unverified"
}

# The original 25-reaction inventory is immutable provenance.
# The 400/1000 W research case deliberately *lumps* O(1D) and O(1S)
# into one effective solver Os/O(ex) state, while preserving original HPEM
# physical reaction identities in the 25-row REACTIONS provenance ledger.
# EI-936 has a separate rate and 4.19 eV loss; no distinct O(1S) transport.
ACTIVE_EXCLUDED_REACTION_IDS = frozenset()
SOLVER_SPECIES_IDENTITY = {
    "O(3P)": "O",
    "O(1D)": "Os",
    "O(1S)": "Os",
    "O(ex)": "Os",
    "O2(a1Delta_g)": "O2s",
}
# EI-413 and EI-414 are deliberately assigned to the tracked O2(a) lump.
# The original 25-row table remains unmodified scientific provenance.
ACTIVE_REACTIONS = tuple(
    (rid, reactants, "e O2a", model)
    if rid in {"413", "414"}
    else (rid, reactants, "e O1D", "formula")  # EI-936 analytic fallback; optional lookup in runtime overlay.
    if rid == "936"
    else (rid, reactants, products, model)
    for rid, reactants, products, model in REACTIONS
    if rid not in ACTIVE_EXCLUDED_REACTION_IDS
)


def active_audit():
    """Audit the opt-in 25-channel O(ex) effective model, not the historical physical ledger."""
    canonical = audit()
    assert canonical["reaction_count"] == 25
    assert len(ACTIVE_REACTIONS) == 25
    assert {r[0] for r in REACTIONS} == {r[0] for r in ACTIVE_REACTIONS}
    assert sum(r[3] == "lookup" for r in ACTIVE_REACTIONS) == 19
    assert sum(r[3] == "formula" for r in ACTIVE_REACTIONS) == 3
    assert sum(r[3] == "heavy" for r in ACTIVE_REACTIONS) == 3
    for reaction in ACTIVE_REACTIONS:
        delta = stoich(reaction)
        assert sum(v * SPECIES[s][0] for s, v in delta.items()) == 0, reaction[0]
        assert sum(v * SPECIES[s][1] for s, v in delta.items()) == 0, reaction[0]
    active_ids = {r[0] for r in ACTIVE_REACTIONS}
    assert {"935", "936", "943", "407", "413", "414"}.issubset(active_ids)
    assert stoich(next(r for r in ACTIVE_REACTIONS if r[0] == "936")) == {"O": -1, "O1D": 1}
    for rid in ("407", "413", "414"):
        reaction = next(r for r in ACTIVE_REACTIONS if r[0] == rid)
        assert stoich(reaction) == {"O2": -1, "O2a": 1}, rid
    for rid in ("411", "2068", "2073"):
        reaction = next(r for r in ACTIVE_REACTIONS if r[0] == rid)
        assert stoich(reaction) == {"O2": -1, "O": 2} if rid == "411" else stoich(reaction) == {"O2a": -1, "O": 2}
    assert {"H23", "H24", "H25"}.issubset(active_ids)
    return {
        "scope": "400W_1000W_research_active_chemistry",
        "canonical_inventory": 25,
        "active_reactions": 25,
        "active_lookup_tables": 19,
        "optional_lookup_tables": ["936"],
        "formula_reactions": 3,
        "heavy_reactions": 3,
        "excluded_reactions": sorted(ACTIVE_EXCLUDED_REACTION_IDS),
        "source_species_mapping": SOLVER_SPECIES_IDENTITY,
        "missing_transport_species": [],
        "lumped_O2a_production_reaction_ids": ["407", "413", "414"],
        "user_selected_O3P_dissociation_reaction_ids": ["411", "2068", "2073"],
        "heavy_research_reaction_ids": ["H23", "H24", "H25"],
        "legacy_Zhao_dissociation_parallel_activation_allowed": False,
        "lumped_O2a_source_model": "user_selected_surrogate_not_state_resolved_branching",
        "lumped_energy_losses_eV": {"407": 0.977, "413": 8.4, "414": 10.0},
        "science_holds": {k: ("User-selected O2(a) effective lumping; physical branching not validated"
                             if k in {"413", "414"} else v)
                          for k, v in KNOWN_SCIENCE_HOLDS.items() if k in active_ids},
        "ei936_species_source_enabled": True,
        "ei936_energy_sink_enabled": True,
        "ei936_effective_product": "O(ex)/Os",
        "ei936_energy_loss_eV": 4.19,
        "ei936_rate_mode_default": "analytic_maxwellian_fallback",
        "ei936_rate_mode_if_table_available": "lookup",
        "power_run": "NOT_RUN",
        "status": "STOICHIOMETRY_ONLY_PASS",
    }


def stoich(reaction):
    _, reactants, products, _ = reaction
    diff={s:products.split().count(s)-reactants.split().count(s) for s in SPECIES}
    return {s:v for s,v in diff.items() if v}

def audit():
    assert len(REACTIONS)==25
    ids=[x[0] for x in REACTIONS]
    assert len(set(ids))==25
    assert sum(x[3]=="lookup" for x in REACTIONS)==20
    assert sum(x[3]=="formula" for x in REACTIONS)==2
    assert sum(x[3]=="heavy" for x in REACTIONS)==3
    for item in REACTIONS:
        delta=stoich(item)
        atoms=sum(v*SPECIES[s][0] for s,v in delta.items())
        charge=sum(v*SPECIES[s][1] for s,v in delta.items())
        if atoms!=0 or charge!=0:
            raise AssertionError(f"{item[0]} atoms={atoms} charge={charge}")
    assert stoich(next(x for x in REACTIONS if x[0]=="415"))=={"e":1,"O2":-1,"O2p":1}
    assert stoich(next(x for x in REACTIONS if x[0]=="417"))=={"e":1,"O2":-1,"O":1,"Op":1}
    return {
        "reaction_count":25, "lookup_count":20, "formula_count":2,
        "heavy_count":3,"conservation":"PASS",
        "missing_transport_species":["O2star","O1S"],
        "science_holds":KNOWN_SCIENCE_HOLDS,
        "powered_ICP_run":"NOT_RUN"
    }

if __name__=="__main__":
    import json
    print(json.dumps(audit(),indent=2))
