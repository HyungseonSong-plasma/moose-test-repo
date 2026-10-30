"""Materialized Stage-B4 powered inlet Receiver contract for 200 sccm."""
import importlib.util
import math
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"experiments/Issue395_powered_chemistry_ladder/build_oxygen_icp_200sccm_inlet.py"

def _load():
    spec=importlib.util.spec_from_file_location("chem24_inlet",SCRIPT)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def _baseline():
    names=("neutral_inlet_mdot","neutral_inlet_mdot_O2",
           "neutral_inlet_mdot_O2s","neutral_inlet_mdot_O","neutral_inlet_mdot_Os")
    return ("[Postprocessors]\n"+
            "".join(f"  [{name}]\n    type = Receiver\n    default = 1.0\n  []\n"
                    for name in names)+"[]\n")

def test_five_stageb4_receivers_convert_and_balance():
    m=_load()
    result=m.apply(_baseline())
    cfg=m.json.loads(m.CONFIG.read_text())["inlet"]
    mass=cfg["mass_fractions"]
    expect={
        "neutral_inlet_mdot":cfg["total_mass_flow_kg_s"],
        "neutral_inlet_mdot_O2":cfg["total_mass_flow_kg_s"]*mass["Yin_O2"],
        "neutral_inlet_mdot_O2s":cfg["total_mass_flow_kg_s"]*mass["Yin_O2s"],
        "neutral_inlet_mdot_O":cfg["total_mass_flow_kg_s"]*mass["Yin_O"],
        "neutral_inlet_mdot_Os":cfg["total_mass_flow_kg_s"]*mass["Yin_Os"],
    }
    for name,n in expect.items():
        actual=m.re.search(rf"(?ms)^  \[{name}\]\n(?P<body>.*?)^  \[\]$",result)
        assert actual is not None
        numeric=float(m.re.search(r"default = ([0-9.eE+-]+)",actual.group("body")).group(1))
        assert math.isclose(numeric,n,rel_tol=1e-13)
    assert len(m.re.findall(r"default = ",result))==5

def test_missing_or_duplicate_receiver_rejected():
    m=_load()
    with pytest.raises(ValueError,match="neither historical"):
        m.apply(_baseline().replace("[neutral_inlet_mdot_Os]","[renamed]"))
    with pytest.raises(ValueError,match="exactly one"):
        m.apply(_baseline().replace("[]\n[]\n", "[]\n  [neutral_inlet_mdot_O]\n    type = Receiver\n    default = 2\n  []\n[]\n"))
