"""24-channel exploratory oxygen ICP source owner and input preparation regression."""
import importlib.util
import json
import math
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/"experiments/Issue395_powered_chemistry_ladder"

def _load():
    spec=importlib.util.spec_from_file_location("chem24",DIR/"build_oxygen_24_source_overlay.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _base(m):
    return "\n".join(m.REQUIRED)+"\n"

def test_24_stoichiometric_channels_and_rate_owners():
    m=_load()
    assert m.validate_network()["atoms_charge_mass"]=="PASS"
    assert len(m.LOOKUP_IDS)==19
    assert len(m.FORMULA_IDS)==2
    assert len(m.HEAVY_IDS)==3
    assert 936 not in m.CHEM
    assert m.CHEM[413]==m.CHEM[414]=={"O2":-1,"O2a":1}
    assert m.CHEM[411]==m.CHEM[412]=={"O2":-1,"O":2}
    assert m.CHEM[2068]==m.CHEM[2073]=={"O2a":-1,"O":2}
    assert m.CHEM[2074]=={"e":1,"O2a":-1,"Op":1,"O":1}
    assert m.CHEM[2259]=={"e":-1,"O2p":-1,"O":2}
    assert m.CHEM[2738]=={"e":1,"Om":-1,"O":1}

def test_source_projection_one_source_per_variable_and_heavy_units():
    m=_load()
    overlay=m.make_overlay({i:f"private_rates/r{i}.txt" for i in m.LOOKUP_IDS},_base(m))
    assert overlay.count("type = PhysicsElectronImpactRateMaterial")==19
    assert overlay.count("reaction_progress = R_") == 19
    assert overlay.count("property_name = R_2259")==1
    assert overlay.count("property_name = R_2738")==1
    assert overlay.count("property_name = R_H23")==1
    assert overlay.count("property_name = R_H24")==1
    assert overlay.count("property_name = R_H25")==1
    assert "2.4e-13*(300.0/(te*11604.51812155))^0.70*ne*c" in overlay
    assert "2.0e-13*exp(-5.5/te)*ne*c" in overlay
    assert f"{1e-13*m.N_A:.17g}*a*b" in overlay
    assert f"{2e-17*m.N_A:.17g}*(300.0/t)^0.4*a*b" in overlay
    for name in ("w_O","w_Os","w_O2s","log_ni","log_nm","log_nop",
                 "log_ne","log_energy","p"):
        assert overlay.count(f"variable = {name}\n")==1
    assert "variable = w_O2_constraint" not in overlay
    assert "variable = w_O2p" not in overlay
    assert "R_936" not in overlay
    assert "R_diss_O2" not in overlay
    assert "S_energy_chem24" in overlay
    assert "S_mass_closure_chem24" in overlay
    assert "S_charge_closure_chem24" in overlay
    assert "R_2074" in overlay
    for monitor in ("n_O2_X_avg","n_O2_a_avg","n_O_3P_avg","n_O_1D_avg"):
        assert f"[{monitor}]" in overlay
    assert "csv = true" in overlay
    # These are separate progress owners but only one species source per
    # field, preventing accidental repetition of earlier single-EI overlays.

def test_parsed_functor_symbols_avoid_moose_reserved_names():
    m=_load()
    overlay=m.make_overlay({i:f"private_rates/r{i}.txt" for i in m.LOOKUP_IDS},_base(m))
    # MOOSE ParsedFunctorMaterial appends x,y,z,t and defines pi/e.
    assert "functor_symbols = 'a b tempK'" in overlay
    assert "(300.0/tempK)^0.4*a*b" in overlay
    assert "functor_symbols = 'el o2p op om'" in overlay
    assert "expression = '-el+o2p+op-om'" in overlay
    import re
    reserved={"x","y","z","t","pi","e"}
    for aliases in re.findall(r"functor_symbols = '([^']+)'", overlay):
        names=aliases.split()
        assert not reserved.intersection(names)
        assert len(names)==len(set(names))
    for name in sorted(reserved):
        with pytest.raises(ValueError, match="reserved parsed functor symbol"):
            m.parsed("bad","S_bad",["T_g"],[name],name)
    with pytest.raises(ValueError, match="duplicate parsed functor symbol"):
        m.parsed("bad","S_bad",["T_g","rho_neutral"],["v","v"],"v")
    with pytest.raises(ValueError, match="invalid parsed functor symbol"):
        m.parsed("bad","S_bad",["T_g"],["bad-name"],"bad-name")


def test_strict_lookup_100point_all19_and_private_stage(tmp_path):
    m=_load()
    private=tmp_path/"incoming"
    private.mkdir()
    for rid,target in m.PARENT.items():
        name={"O2":"O2_X","O2a":"O2_a1Delta","O":"O_3P","Os":"O_1D"}[target]
        (private/f"EI-{rid}_{name}.txt").write_text(
            "# E [eV] rate [m3/(mol s)]\n"+
            "".join(f"{1.5+0.25*i:.15g} {1e8+rid+i:.15g}\n" for i in range(100)))
    baseline=tmp_path/"powered_base.i"
    baseline.write_text(_base(m))
    out=tmp_path/"experiment"/"chem24.i"
    report=m.stage(baseline,private,out,tmp_path)
    assert report["active"]==24 and report["lookups"]==19
    assert out.is_file()
    assert len(list((out.parent/"private_rates").glob("EI-*.txt")))==19
    overlay = out.read_text()
    # MOOSE resolves relative lookup paths against the overlay input folder.
    # A path prefixed with experiment/ here would point to a nonexistent
    # experiment/experiment/private_rates directory.
    for rid, parent in m.PARENT.items():
        suffix = {"O2":"O2_X","O2a":"O2_a1Delta",
                  "O":"O_3P","Os":"O_1D"}[parent]
        relative = f"private_rates/EI-{rid}_{suffix}.txt"
        assert f"rate_table_file = '{relative}'" in overlay
        assert (out.parent / relative).is_file()
    assert "rate_table_file = 'experiment/private_rates/" not in overlay
    assert len(json.loads((out.parent/"chem24_manifest.json").read_text())["lookup_sha256"])==19
    broken=private/"EI-2074_O2_a1Delta.txt"
    broken.write_text("1.5 1\n")
    with pytest.raises(ValueError, match="expected 100"):
        m.validate_files(private)

def test_fail_closed_legacy_duplicate_and_missing_rate_owners():
    m=_load()
    with pytest.raises(ValueError, match="inherited"):
        m.make_overlay({i:f"r{i}" for i in m.LOOKUP_IDS},_base(m)+"\nR_ion_O2\n")
    with pytest.raises(ValueError, match="all 19"):
        m.make_overlay({407:"r"},_base(m))

def test_power_replay_research_mode_must_skip_legacy_chemistry():
    s=(DIR/"issue397_l1_power_scan_replay.sh").read_text()
    assert "OXYGEN_RESEARCH_FULL24" in s
    assert "build_oxygen_24_source_overlay.py" in s
    assert "OXYGEN_RESEARCH_RATE_DIR" in s
    assert "FULL24_EXTRA_INPUT" in s
    assert "OXYGEN_RESEARCH_LUMPED_O2A" in s
    assert "OXYGEN_RESEARCH_EI2738_FORMULA" in s
    assert 'python3 bin/physics.py preflight --self-test' in s
    assert 'python3 bin/physics.py preflight "$FULL24_OVERLAY"' in s
