"""HPEM EI-2074 process-specific numeric evidence and lookups are distinct from EI-417."""
import json
from pathlib import Path

CFG=Path(__file__).resolve().parents[1] / "experiments/Issue395_powered_chemistry_ladder/oxygen_icp_operating_200sccm_sticking1.json"

def test_2074_dedicated_lookup_is_selected_for_exploratory_case():
    c=json.loads(CFG.read_text())["chemistry"]
    x=c["ei2074"]
    assert x["rate_mode"]=="lookup"
    assert x["special_number"] == 2074
    assert x["source_process_label"] == "O2* > O^ + O + E + E"
    assert x["source_cross_section_points"] == 1001
    assert x["source_threshold_eV"] == 16.023
    assert x["rate_points"] == 100
    assert x["rate_file_private"] == "EI-2074_O2_a1Delta.txt"
    assert "not shifted-EI417" in x["physics_policy"]
    assert "not proof" in x["validation_distinction"]
    assert c["ei412"]["rate_mode"] == "lookup"
    assert c["ei2259"]["rate_mode"] == "formula"
    assert c["ei2738"]["rate_mode"] == "formula"
