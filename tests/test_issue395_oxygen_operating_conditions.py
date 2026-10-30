import json, math, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/"experiments/Issue395_powered_chemistry_ladder"

def test_200sccm_sticking1_research_contract():
    d=json.loads((FOLDER/"oxygen_icp_operating_200sccm_sticking1.json").read_text())
    assert d["rf_targets_w"] == [400,1000]
    i=d["inlet"]
    mdot=(i["Q_sccm"]*1e-6/60)*0.032/i["Vm_std_m3_per_mol"]
    assert math.isclose(mdot,4.759015359722074e-6,rel_tol=1e-12)
    assert math.isclose(i["total_mass_flow_kg_s"],mdot,rel_tol=1e-12)
    w=d["wall"]
    assert w["research_uniform_sticking"] is True
    for name in ("O","O2s","Os","O2p","Om","Op"):
        assert w[f"{name}_sticking_coefficient"]==1
    assert w["exclude_boundaries"]==["inlet","outlet"]
    assert w["secondary_emission_coefficient"]==0
    historic=(ROOT/"experiments/Issue27_surface_reactions/controlled_wall/combined.py").read_text()
    assert 'parameters.get("research_uniform_sticking", False)' in historic
    assert '"O_sticking_coefficient": 1.0 if research_uniform else 0.2' in historic

def test_inlet_replacer_retains_fresh_base_and_massflow():
    import importlib.util
    script=FOLDER/"build_oxygen_icp_200sccm_inlet.py"
    spec=importlib.util.spec_from_file_location("icp_inlet_research",script)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    source="Q_sccm = 100\nVm_std = 0.0224136\nQ_std = 1.0\n"
    source+="".join(f"{key} = {0.7 if key=='Yin_O2' else 0.05}\n" for key in mod.FRACTIONS)
    source+="inlet_mdot_value = STANDARD_MASSFLOW_EXPRESSION\n"
    result=mod.apply(source)
    assert re.search(r"(?m)^Q_sccm = 200$",result)
    assert re.search(r"(?m)^Yin_O2 = 1$",result)
    for key in mod.FRACTIONS:
        if key!="Yin_O2":
            assert re.search(rf"(?m)^{key} = 0$",result)
    assert result.count("inlet_mdot_value") == 1
