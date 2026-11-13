"""P0 contract for explicit EI/H rate owners and root ideal-gas Functors.

No P3 kinetic parity or runtime conservation is claimed by these static tests.
"""
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "physics_app/src"
APP = ROOT / "physics_app"
R = 8.31446261815324


def test_only_explicit_ei_and_h_rate_factory_names():
    for old in ("RateCoeffMaterial", "HeavyReactionRateMaterial"):
        assert not (APP / "include/materials" / (old + ".h")).exists()
        assert not (APP / "src/materials" / (old + ".C")).exists()
    for name in ("EIRateCoefMaterial", "HRateCoefMaterial"):
        header = (APP / "include/materials" / (name + ".h")).read_text()
        source = (APP / "src/materials" / (name + ".C")).read_text()
        assert f"class {name} : public FunctorMaterial" in header
        assert f'registerMooseObject("PhysicsApp", {name});' in source
        assert "registerMooseObjectAliased" not in source


def test_plasmas_root_owns_only_p_t_and_ideal_gas_model():
    header = (APP / "include/physics/plasma/Chemistry.h").read_text()
    source = (SRC / "physics/plasma/Chemistry.C").read_text()
    assert "void act() override;" in header
    assert 'params.addParam<Real>("pressure"' in source
    assert 'params.addParam<Real>("temperature"' in source
    assert 'MooseEnum("ideal_gas", "ideal_gas")' in source
    assert 'add("p", pressure_literal.str(), {}, {});' in source
    assert 'add("T", temperature_literal.str(), {}, {});' in source
    assert 'add("rho_g", "pressure/(8.31446261815324*temp*(' in source
    assert 'add("n_g", "pressure/(1.380649e-23*temp)"' in source
    assert 'add("M_mix", "1/(" + denominator' in source
    assert "GasStateMaterial" not in header + source or (
        # Source comment can document why a custom class is unnecessary.
        '"GasStateMaterial"' not in source
    )
    assert not (APP / "src/materials/GasStateMaterial.C").exists()


def test_all_transport_owners_use_common_p_and_t_when_present():
    interface = (SRC / "physics/plasma/PlasmaInterface.C").read_text()
    nv = (SRC / "physics/plasma/NVTransport.C").read_text()
    dd = (SRC / "physics/plasma/DDContinuityEq.C").read_text()
    assert "rootGasStateEnabled()" in interface
    for source in (nv, dd):
        assert 'rootGasStateEnabled() ? "p"' in source
        assert 'rootGasStateEnabled() ? "T"' in source


def test_surface_input_is_real_ideal_gas_wiring_and_composition():
    sample = (APP / "ci/json_surface_rate_p2.i").read_text()
    data = json.loads((APP / "ci/json_surface_rate_p2.json").read_text())
    assert "pressure = 1.333223684" in sample
    assert "temperature = 300" in sample
    assert "model = ideal_gas" in sample
    assert "temperature = T" in sample
    assert "density = rho_g" in sample
    assert "gas_state" not in data
    assert "prop_names = 'Y_O2 Y_O'" not in sample
    assert data["species"]["O2"]["initial_vol_mass_fraction"] == 0.9
    assert data["species"]["O2"]["initial_inlet_mass_fraction"] == 1.0
    assert data["species"]["O"]["initial_vol_mass_fraction"] == 0.1
    assert data["species"]["O"]["initial_inlet_mass_fraction"] == 0.0
    assert "functor = Y_O2_initial_vol" in sample
    assert "functor = Y_O2_inlet" in sample
    assert "functor = Y_O_inlet" in sample
    assert sum(s["initial_vol_mass_fraction"] for s in data["species"].values()) == 1.0
    assert sum(s["initial_inlet_mass_fraction"] for s in data["species"].values()) == 1.0
    parser = (SRC / "physics/plasma/Chemistry.C").read_text()
    assert 'if (root.contains("gas_state"))' in parser
    assert "initial_vol_mass_fraction" in parser
    assert "initial_inlet_mass_fraction" in parser
    assert "conflicting species identity for " in parser
    assert 'add("Y_" + id + "_initial_vol"' in parser
    assert 'add("Y_" + id + "_inlet"' in parser
    assert "const auto * nv = _data.nvTransport();" in parser
    assert "Initial volume and inlet heavy-species mass fractions must each" in parser


def test_ideal_gas_mixture_molar_mass_and_density_oracle():
    p, T = 1.333223684, 300.0
    for Y in ((1.0, 0.0), (0.8, 0.2), (0.0, 1.0)):
        denominator = Y[0] / 0.032 + Y[1] / 0.016
        M_mix = 1.0 / denominator
        density = p * M_mix / (R * T)
        assert math.isclose(density, p / (R * T * denominator), rel_tol=1e-14)
        assert 0.0 < density < 1.8e-5
    oxygen = p * 0.032 / (R * T)
    assert math.isclose(oxygen, 1.7105e-5, rel_tol=3e-4)
