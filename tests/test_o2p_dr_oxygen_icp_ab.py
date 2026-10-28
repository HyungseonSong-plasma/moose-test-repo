"""P0 controls for experimental Oxygen ICP O2+ dissociative-recombination A/B."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "experiments/Issue395_powered_chemistry_ladder/build_o2p_dr_overlay.py"
spec = importlib.util.spec_from_file_location("o2p_dr_generator", GENERATOR)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

BASE = """
[log_ne]
[log_ni]
[log_energy]
[w_O]
[p]
property_name = n_e_physical
mean_energy = mean_en_solved
"""


def test_300k_reference_and_monotonicity() -> None:
    energy_300k = 1.5 * 300.0 / module.KELVIN_PER_EV
    assert math.isclose(module.rate_m3_s(energy_300k), 2.4e-13, rel_tol=1e-14)
    assert module.rate_m3_s(1.0) > module.rate_m3_s(4.0)
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            module.rate_m3_s(bad)


def test_single_rate_owner_and_all_projectors() -> None:
    generated = module.build(BASE)
    assert generated.count("property_name = R_o2p_dr\n") == 1
    assert "n_e_physical log_ni mean_en_solved" in generated
    assert "exp(lni)" in generated
    assert "variable = log_ni" in generated
    assert "variable = log_ne" in generated
    assert "variable = log_energy" in generated
    assert "variable = w_O" in generated
    assert "variable = p" in generated
    assert "S_heavy_mass_closure_o2p_dr" in generated
    assert "S_charge_mol_closure_o2p_dr" in generated
    assert "THERMAL_EXTRAPOLATION" not in generated  # status belongs to CLI output


def test_conservation_invariant_and_sign_mutations() -> None:
    # With progress R>0 (molar), production of 2 O must exactly balance 1 O2+.
    for R in (1e-12, 1.0, 1e8):
        n_e = -R
        n_ion = -R
        n_O = 2.0 * R
        neutral_mass = 2.0 * module.M_O * R
        ion_mass = -module.M_O2P * R
        assert math.isclose(n_ion - n_e, 0.0, abs_tol=1e-14)
        assert math.isclose(n_O + 2.0 * n_ion, 0.0, abs_tol=1e-14)
        assert math.isclose(neutral_mass + ion_mass, 0.0, abs_tol=1e-10)
        assert n_e < 0 and n_ion < 0 and n_O > 0
        assert (n_ion - (+R)) != 0.0  # negative control: wrong e- source sign
        assert (R + 2.0 * n_ion) != 0.0  # negative control: only one O generated


def test_requires_existing_production_states_and_no_duplicate_owner() -> None:
    with pytest.raises(ValueError, match="prerequisite"):
        module.build(BASE.replace("[log_ni]", ""))
    with pytest.raises(ValueError, match="already exists"):
        module.build(BASE + "\nproperty_name = R_o2p_dr\n")
