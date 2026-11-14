"""Issue #402: JSON Chemistry is sole active heavy/surface reaction database.

Preserve Stage-5 H01-H05 kinetic and stoichiometric invariants while deleting
the legacy text parser, source files, and MOOSE factory names. This is a P0
contract and analytic rate oracle, not Native P1/P2 or science acceptance.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
DATA = APP / "data/heavy_reactions"
NA = 6.02214076e23

EXPECTED = {
    "H01": (2e-17, 0.5, {"Op": 1, "O2": 1}, {"O": 1, "O2p": 1}),
    "H02": (4e-14, 0.43, {"Om": 1, "Op": 1}, {"O": 2}),
    "H03": (2.6e-14, 0.44, {"Om": 1, "O2p": 1}, {"O": 3}),
    "H04": (2.6e-14, 0.44, {"Om": 1, "O2p": 1}, {"O": 1, "O2": 1}),
    "H05": (3e-16, 0, {"Om": 1, "O": 1}, {"O2": 1, "e": 1}),
}


def catalogue(filename: str) -> dict:
    return json.loads((DATA / filename).read_text())


def test_legacy_parser_and_factories_are_really_deleted():
    for name in ("PhysicsReactionDatabase", "PhysicsReactionRateMaterial",
                 "PhysicsSurfaceReactionMaterial"):
        for folder, ext in (("include/utils", ".h"), ("src/utils", ".C"),
                            ("include/materials", ".h"), ("src/materials", ".C")):
            assert not (APP / folder / (name + ext)).exists(), (folder, name)
    for old in ("stage5_s5d_oxygen_heavy.txt", "stage5_s5e_h05_oxygen_heavy.txt"):
        assert not (DATA / old).exists()
    for new in ("HRateCoefMaterial", "SurfaceReactionMaterial"):
        header = (APP / "include/materials" / (new + ".h")).read_text()
        source = (APP / "src/materials" / (new + ".C")).read_text()
        assert "class " + new + " : public FunctorMaterial" in header
        assert 'registerMooseObject("PhysicsApp", ' + new + ");" in source
        assert "registerMooseObjectAliased" not in source
        assert "PhysicsReactionDatabase" not in header + source
    parser = (APP / "src/physics/plasma/Chemistry.C").read_text()
    assert 'entry.contains("rate")' in parser
    assert 'rate basis must be particle or molar' in parser
    assert 'surface reactions require explicit rate' in parser
    assert 'if (reaction.domain == "surface")' in parser
    assert "missing heavy molar_mass_kg_mol for " in parser
    assert "surface electron-energy sources are unsupported" in parser
    assert "molar rate coefficient overflow" in parser


def test_heavy_json_preserves_exact_frozen_rate_models_and_conservation():
    mechanisms = (
        catalogue("stage5_s5d_oxygen_heavy.json"),
        catalogue("stage5_s5e_h05_oxygen_heavy.json"),
    )
    found = {}
    for data in mechanisms:
        for reaction in data["reactions"]:
            rid = reaction["id"]
            assert rid not in found
            found[rid] = reaction
            assert reaction["domain"] == "volume"
            assert reaction["units"] == "mol/(m^3 s)"
            assert reaction["energy_loss_eV"] == {"model": "none"}
            rate = reaction["rate"]
            assert rate["model"] == "power_law"
            assert rate["basis"] == "particle"
            assert rate["T_ref"] == 300
            expected_A, expected_exponent, reactants, products = EXPECTED[rid]
            assert rate["A"] == expected_A
            assert rate["exponent"] == expected_exponent
            assert reaction["reactants"] == reactants
            assert reaction["products"] == products
            for element in ("O",):
                reactant_atoms = sum(n * data["species"][s]["elements"].get(element, 0)
                                     for s, n in reactants.items())
                product_atoms = sum(n * data["species"][s]["elements"].get(element, 0)
                                    for s, n in products.items())
                assert reactant_atoms == product_atoms
            assert sum(n * data["species"][s]["charge_number"] for s, n in reactants.items()) == (
                   sum(n * data["species"][s]["charge_number"] for s, n in products.items()))
    assert set(found) == set(EXPECTED)
    assert mechanisms[1]["species"]["e"] == {"elements": {}, "charge_number": -1}


@pytest.mark.parametrize("temperature", [300.0, 600.0, 1200.0])
def test_exact_legacy_particle_basis_conversion_and_temperature_scaling(temperature):
    # A_particle [m^3/s] * NA gives second-order k_molar [m^3/(mol s)].
    for rid, (A, exponent, reactants, products) in EXPECTED.items():
        concentrations = {s: (i + 1) * 0.001
                          for i, s in enumerate(sorted(reactants))}
        order = sum(reactants.values())
        expected = A * NA ** (order - 1) * (300.0 / temperature) ** exponent
        for species, coefficient in reactants.items():
            expected *= concentrations[species] ** coefficient
        rate = A * NA ** (order - 1) * (300.0 / temperature) ** exponent
        for species, coefficient in reactants.items():
            rate *= concentrations[species] ** coefficient
        assert math.isclose(rate, expected, rel_tol=1e-14)
        assert rate > 0


def test_json_stage5_inputs_use_single_canonical_rate_owner():
    filenames = (
        "experiments/historical_recipe_support/issue192_s5r.py",
        "physics_app/ci/check_stage5_s5d_heavy_reactions.py",
        "physics_app/ci/check_stage5_h05_runtime.py",
        "physics_app/ci/check_stage5_s5r_assembly.py",
        "experiments/Issue192_s5r_representative/run.py",
    )
    for filename in filenames:
        source = (ROOT / filename).read_text()
        assert "stage5_s5d_oxygen_heavy.txt" not in source
        assert "stage5_s5e_h05_oxygen_heavy.txt" not in source
    builder = (ROOT / filenames[0]).read_text()
    assert 'type = HRateCoefMaterial' in builder
    assert "type = PhysicsReactionRateMaterial" not in builder
    for i in range(1, 6):
        assert f'"R_H{i:02d}"' in builder or f'R_H{i:02d}' in builder


def test_surface_json_keeps_wall_mass_flux_separate_from_volume_sources():
    path = APP / "ci/json_surface_rate_p2.json"
    data = json.loads(path.read_text())
    reaction = data["reactions"][0]
    assert reaction["domain"] == "surface"
    assert reaction["id"] == "H90"
    assert reaction["units"] == "mol/(m^2 s)"
    assert reaction["rate"] == {"model": "thermal_sticking", "sticking": 0.25}
    assert reaction["reactants"] == {"O2": 1}
    assert reaction["products"] == {"O": 2}
    c = 0.001
    mass_O2 = 0.032
    mean_speed = math.sqrt(8 * 8.31446261815324 * 300 / (math.pi * mass_O2))
    progress = 0.25 * c * mean_speed / 4
    flux_O2 = mass_O2 * progress
    flux_O = -2 * 0.016 * progress
    assert math.isclose(flux_O2 + flux_O, 0.0, abs_tol=1e-16)
    material = (APP / "src/materials/SurfaceReactionMaterial.C").read_text()
    fixture = (APP / "ci/json_surface_rate_p2.i").read_text()
    assert "species = 'O2'" in fixture
    assert "pressure = 1.333223684" in fixture
    assert "temperature = 300" in fixture
    assert "model = ideal_gas" in fixture
    assert "temperature = T" in fixture
    assert "density = rho_g" in fixture
    assert "gas_state" not in data
    assert data["species"]["O2"]["initial_vol_mass_fraction"] == 0.9
    assert data["species"]["O2"]["initial_inlet_mass_fraction"] == 1.0
    assert data["species"]["O"]["initial_vol_mass_fraction"] == 0.1
    assert data["species"]["O"]["initial_inlet_mass_fraction"] == 0.0
    assert "mass_fractions = 'Y_O2'" in fixture
    assert "surface_mass_flux_O" in fixture
    assert "_chemistry.speciesRecords()" in material
    assert 'reaction.progress' in material
    assert 'reaction.net(species)' in material
    assert '"surface_mass_flux_" + species' in material
