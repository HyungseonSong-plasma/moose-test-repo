"""Review contracts: full merged S6 JSON and temporary e_transport table."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
PILOT=ROOT/"experiments/Issue402_plasma_dsl_g1"

def test_review_json_all_reactions_and_transport_bindings():
    base=json.loads((PILOT/"chemistry/oxygen_s6_common.json").read_text())
    for variant in ("417","941"):
        delta=json.loads((PILOT/f"chemistry/oxygen_s6_{variant}.json").read_text())
        preview=json.loads((PILOT/f"chemistry/review_s6_{variant}_full.json").read_text())
        assert set(preview["species"]) == set(base["species"])
        for name, source in base["species"].items():
            assert {key: preview["species"][name][key] for key in source} == source
        assert preview["reactions"]==base["reactions"]+delta["reactions"]
        assert set(preview["equations"])==set(base["equations"])|set(delta["equations"])
        assert len(preview["reactions"])==8
        assert "transport_coefficients" not in preview
        dd=preview["species"]
        assert dd["e"]["energy_transport_coef"] == "fluid"
        assert "coordinate" not in dd["e"]
        assert dd["e"]["transport_coef"] == "lookup"
        assert dd["e"]["table_file"] == "e_transport.txt"
        assert (PILOT/"chemistry"/dd["e"]["table_file"]).is_file()
        for name in ("O2p","Om","Op"):
            assert dd[name]["transport_coef"] == "functor"
            assert dd[name]["mobility"] == name + "_mobility"
            assert dd[name]["diffusivity"] == name + "_diffusivity"
        text=(PILOT/f"review_s6_{variant}_input_overlay.i").read_text()
        assert f"files = 'chemistry/review_s6_{variant}_full.json'" in text
        assert "fem_species = 'e'" in text and "fvm_species = 'O2p Om Op'" in text
        assert "[FunctorMaterials]" not in text
        assert text.count("type = DDTransportMaterial")==0
        assert "NOT a standalone" in text or "not a standalone" in text

def test_provisional_transport_is_not_misrepresented():
    table=(PILOT/"chemistry/e_transport.txt").read_text()
    reference=(ROOT/"physics_app/ci/electron_energy_lookup_response_smoke_table.txt").read_text()
    assert "PROVISIONAL P2 TABLE ONLY" in table
    assert "NOT a verified Boltzmann" in table
    assert table.endswith(reference)
    synthetic=json.loads((PILOT/"plasma_auto_constant.json").read_text())
    assert {k for k,v in synthetic["species"].items() if "transport_coef" in v} == {"e","O2p","Om","Op"}
    assert "transport_coefficients" not in synthetic
