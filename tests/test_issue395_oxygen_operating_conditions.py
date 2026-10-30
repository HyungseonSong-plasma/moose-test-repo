"""Fixed Boltzmann mixture -> SI MOOSE inlet composition; keep existing ion seeds."""
from __future__ import annotations

import importlib.util
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "experiments" / "Issue395_powered_chemistry_ladder"
CONFIG = FOLDER / "oxygen_icp_operating_200sccm_sticking1.json"


def test_200sccm_sticking1_research_contract():
    d = json.loads(CONFIG.read_text())
    assert d["rf_targets_w"] == [400, 1000]
    inlet = d["inlet"]
    x = inlet["mole_fractions"]
    assert x == {"O2_X": 0.99997, "O2_a1Delta": 1e-5, "O_3P": 1e-5, "O_1D": 1e-5}
    mass = inlet["mass_fractions"]
    assert math.isclose(sum(mass.values()), 1.0, abs_tol=1e-12)
    mean_molar_mass = sum(x[k]*inlet["molar_masses_kg_per_mol"][k] for k in x)
    mdot = (inlet["Q_sccm"]*1e-6/60)*mean_molar_mass/inlet["Vm_std_m3_per_mol"]
    assert math.isclose(mdot, 4.758967769568476e-6, rel_tol=1e-12)
    assert math.isclose(inlet["total_mass_flow_kg_s"], mdot, rel_tol=1e-12)
    assert mass["Yin_O2s"] > 0
    assert mass["Yin_O"] > 0 and mass["Yin_Os"] > 0
    for k in ("Yin_O2p", "Yin_Om", "Yin_Op"):
        assert mass[k] == 0
    initial = d["initial_conditions"]
    charged = initial["charged_species_number_density_m3"]
    assert charged == {"electron":1e15, "O2_plus":1e15, "O_plus":1e12, "O_minus":1e12}
    assert charged["O2_plus"]+charged["O_plus"] == charged["electron"]+charged["O_minus"]
    assert initial["neutral_bulk_initialization_policy"].startswith("preserve")
    wall = d["wall"]
    assert wall["research_uniform_sticking"] is True
    for k in ("O", "O2s", "Os", "O2p", "Om", "Op"):
        assert wall[f"{k}_sticking_coefficient"] == 1
    assert wall["exclude_boundaries"] == ["inlet", "outlet"]
    historic = (ROOT/"experiments/Issue27_surface_reactions/controlled_wall/combined.py").read_text()
    assert 'parameters.get("research_uniform_sticking", False)' in historic


def test_mixture_inlet_replacer_keeps_baseline_massflow():
    spec = importlib.util.spec_from_file_location("oxygen_inlet", FOLDER/"build_oxygen_icp_200sccm_inlet.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    source = "Q_sccm = 100\nVm_std = 0.0224136\nQ_std = 1.0\n"
    source += "".join(f"{key} = 0.1\n" for key in mod.FRACTIONS)
    source += "inlet_mdot_value = STANDARD_MASSFLOW_EXPRESSION\n"
    result = mod.apply(source)
    expected = json.loads(CONFIG.read_text())["inlet"]["mass_fractions"]
    assert re.search(r"(?m)^Q_sccm = 200$", result)
    for key, value in expected.items():
        m = re.search(rf"(?m)^{key} = ([^\n]+)$", result)
        assert m is not None
        assert math.isclose(float(m.group(1)), value, rel_tol=1e-14, abs_tol=1e-16)
    assert result.count("inlet_mdot_value =") == 1


def test_reject_mole_mass_mismatch():
    spec = importlib.util.spec_from_file_location("oxygen_inlet_reject", FOLDER/"build_oxygen_icp_200sccm_inlet.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    config = json.loads(CONFIG.read_text())
    config["inlet"]["mass_fractions"]["Yin_O"] *= 2
    try:
        mod.validated_mass_fractions(config)
    except ValueError as err:
        assert "mole-to-mass" in str(err)
    else:
        raise AssertionError("incorrect mass fraction accepted")
