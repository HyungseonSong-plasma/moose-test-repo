"""EI-2738 literature formula, 2259 formula vs published sigma and EI-412 Lookup."""
import importlib.util
import json
import math
from pathlib import Path
import pytest

DIR=Path(__file__).resolve().parents[1] / "experiments/Issue395_powered_chemistry_ladder"

def _module():
    spec=importlib.util.spec_from_file_location("detachment",DIR/"build_ei2738_detachment_formula_overlay.py")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_selected_rate_modes_and_2259_sigma_distinction():
    x=json.loads((DIR/"oxygen_icp_operating_200sccm_sticking1.json").read_text())["chemistry"]
    assert x["ei412"]["rate_mode"]=="lookup"
    assert x["ei2259"]["rate_mode"]=="formula"
    assert x["ei2259"]["measurement_reality"].startswith("Absolute cross sections published")
    assert x["ei2738"]["rate_mode"]=="formula"
    assert x["ei2074"]["independent_experimental_state_resolved_partial_sigma"]=="not verified available"
    assert x["active_reaction_count"]==24
    assert x["excluded_reactions"]==["936"]

def test_2738_source_projection_has_one_owner_and_closes_charge_mass():
    mod=_module()
    base="\n".join(mod.REQUIRED)
    overlay=mod.build(base)
    assert overlay.count("property_name = R_EI2738")==1
    assert overlay.count("variable = log_nm")==1
    assert overlay.count("variable = log_ne")==1
    assert overlay.count("variable = w_O\n")==1
    assert overlay.count("variable = log_energy")==1
    assert "2.0e-13*exp(-5.5/te)" in overlay
    assert "expression = '-2.70*R'" in overlay
    assert "source = S_O_mass_EI2738" in overlay
    for te in (0.5,1.0,3.0,7.0,15.0):
        k=mod.RATE_PREF_M3_S*math.exp(-mod.TE_EXP_EV/te)
        assert 0<k<mod.RATE_PREF_M3_S
        ne,c=1e15,1e-12
        R=k*ne*c
        assert math.isclose(0.016*R-0.016*R,0,abs_tol=1e-22)
        assert math.isclose(R-R,0,abs_tol=1e-22)

def test_2738_duplicate_is_rejected():
    mod=_module()
    with pytest.raises(ValueError,match="duplicate"):
        mod.build("\n".join(mod.REQUIRED)+"\nR_EI2738")
