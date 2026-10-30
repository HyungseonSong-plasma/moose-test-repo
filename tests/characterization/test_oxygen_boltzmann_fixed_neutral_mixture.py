"""Regression guard for user's O2-balance and minor-neutral-density policy."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments/Issue395_powered_chemistry_ladder/OXYGEN_BOLTZMANN_FIXED_NEUTRAL_MIXTURE.json"


def test_minority_neutral_species_are_each_1e_minus_5_of_total_gas():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    x = data["neutral_mole_fractions"]
    assert len(x) == 5
    assert x["O(3P)"] == 1e-5
    assert x["O(1D)"] == 1e-5
    assert x["O(1S)"] == 1e-5
    assert x["O2(a1Delta_g)"] == 1e-5
    assert abs(x["O2(X3Sigma_g_minus)"] - (1-sum(value for key,value in x.items() if key != "O2(X3Sigma_g_minus)"))) < 1e-12
    assert abs(sum(x.values()) - 1.0) < 1e-12


def test_charged_species_do_not_enter_neutral_gas_fraction():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    forbidden = set(data["excluded_from_neutral_normalization"])
    assert forbidden == {"electron", "O-", "O+", "O2+"}
    assert forbidden.isdisjoint(data["neutral_mole_fractions"])
    assert data["gas_number_density_m3"] is None
    assert data["gas_temperature_K"] is None
    assert data["reduced_electric_field_Td"] is None


def test_no_unsupported_excited_oxygen_collision_target_added():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert data["species_with_fraction_but_no_collision_target"] == ["O(1S)"]
    assert set(data["boltzmann_target_aliases"].values()) == {
        "O2(X3Sigma_g_minus)", "O2(a1Delta_g)", "O(3P)", "O(1D)"
    }
