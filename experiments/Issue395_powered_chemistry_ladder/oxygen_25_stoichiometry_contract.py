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
 "936":"untracked O(1S) state; separate heavy transport needed",
 "2259":"formula validated only for equivalent Te=1-7 eV",
 "2738":"formula validated only for equivalent Te=1-7 eV",
 "H25":"reference temperature convention unverified"
}

# The original 25-reaction inventory is immutable provenance.
# The 400/1000 W research case explicitly excludes EI-936 to avoid
# pretending that the currently untracked O(1S) product is represented by Os.
# Stable solver identities come from the canonical Issue17 R0 species ledger:
# O = O(3P), Os = O(1D), O2s = O2(a1Delta_g).
ACTIVE_EXCLUDED_REACTION_IDS = frozenset({"936"})
SOLVER_SPECIES_IDENTITY = {
    "O(3P)": "O",
    "O(1D)": "Os",
    "O2(a1Delta_g)": "O2s",
}
ACTIVE_REACTIONS = tuple(r for r in REACTIONS if r[0] not in ACTIVE_EXCLUDED_REACTION_IDS)


def active_audit():
    """Audit the opt-in 24-reaction model, not its 25-row source catalog."""
    canonical = audit()
    assert canonical["reaction_count"] == 25
    assert len(ACTIVE_REACTIONS) == 24
    assert {r[0] for r in REACTIONS} - {r[0] for r in ACTIVE_REACTIONS} == {"936"}
    assert sum(r[3] == "lookup" for r in ACTIVE_REACTIONS) == 19
    assert sum(r[3] == "formula" for r in ACTIVE_REACTIONS) == 2
    assert sum(r[3] == "heavy" for r in ACTIVE_REACTIONS) == 3
    for reaction in ACTIVE_REACTIONS:
        delta = stoich(reaction)
        assert sum(v * SPECIES[s][0] for s, v in delta.items()) == 0, reaction[0]
        assert sum(v * SPECIES[s][1] for s, v in delta.items()) == 0, reaction[0]
    active_ids = {r[0] for r in ACTIVE_REACTIONS}
    assert {"935", "943"}.issubset(active_ids)
    return {
        "scope": "400W_1000W_research_active_chemistry",
        "canonical_inventory": 25,
        "active_reactions": 24,
        "active_lookup_tables": 19,
        "formula_reactions": 2,
        "heavy_reactions": 3,
        "excluded_reactions": sorted(ACTIVE_EXCLUDED_REACTION_IDS),
        "source_species_mapping": SOLVER_SPECIES_IDENTITY,
        "missing_transport_species": ["O2star"],
        "science_holds": {k: v for k, v in KNOWN_SCIENCE_HOLDS.items()
                          if k in active_ids},
        "ei936_species_source_enabled": False,
        "ei936_energy_sink_enabled": False,
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
