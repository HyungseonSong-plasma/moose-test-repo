"""Source-level contract for solved Y_i(t,x) and initial/inlet IC/BC handoff.

P0 distinguishes input metadata from live species states; native P1/P2 separately
prove all selected MOOSE objects actually exist and their parameter wiring parses.
"""
from __future__ import annotations
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"physics_app"
CODE=APP/"src/physics/plasma/Chemistry.C"
DATA=APP/"ci/json_surface_rate_p2.json"
INPUT=APP/"ci/json_surface_rate_p2.i"


def test_live_owners_are_in_species_and_not_top_level_state_lists():
    obj=json.loads(DATA.read_text())
    assert "gas_state" not in obj
    for id,record in obj["species"].items():
        assert record["mass_fraction_variable"] == "w_"+id
        assert "mass_fraction_functor" not in record
        assert 0 <= record["initial_vol_mass_fraction"] <= 1
        assert 0 <= record["initial_inlet_mass_fraction"] <= 1


def test_root_ideal_gas_has_no_json_initial_as_live_density_input():
    c=CODE.read_text()
    assert "mass_fraction_variable OR a derived mass_fraction_functor" in c or (
        "mass_fraction_variable or" in c and "mass_fraction_functor" in c)
    assert 'add("Y_" + id, "live_y", {live}, {"live_y"});' in c
    assert 'fractions.push_back("Y_" + id);' in c
    assert 'add("Y_" + id, literal(*record.initial_vol_mass_fraction)' not in c
    assert 'names.push_back(fractions[i]);' in c
    assert 'add("rho_g", "pressure/(8.31446261815324*temp*(' in c
    assert 'add("rho_g_initial"' in c and 'add("rho_g_inlet"' in c


def test_root_ic_and_bc_create_only_for_solved_species():
    c=CODE.read_text()
    i=INPUT.read_text()
    assert 'registerMooseAction("PhysicsApp", PlasmasAction, "add_ics_physics");' in c
    assert 'registerMooseAction("PhysicsApp", PlasmasAction, "add_bc");' in c
    assert 'const auto type = "FVConstantIC";' in c
    assert 'const std::string type = "FVDirichletBC";' in c
    assert 'params.set<Real>("value") = *record.initial_vol_mass_fraction;' in c
    assert 'params.set<Real>("value") = *record.initial_inlet_mass_fraction;' in c
    assert 'if (record.mass_fraction_variable.empty())' in c
    assert 'initialize_species_mass_fractions = true' in i
    assert 'inlet_boundaries = left' in i
    assert 'inlet_bc_model = dirichlet' in i
    assert i.count('type = MooseVariableFVReal') == 2


def test_material_consumers_resolve_functor_at_evaluation_not_at_setup():
    paths={
        "HRateCoefMaterial": APP/"src/materials/HRateCoefMaterial.C",
        "NVTransportMaterial": APP/"src/materials/NVTransportMaterial.C",
        "SurfaceReactionMaterial": APP/"src/materials/SurfaceReactionMaterial.C",
        "PhysicsPlasmaChargeDensityMaterial": APP/"src/materials/PhysicsPlasmaChargeDensityMaterial.C",
    }
    for name,path in paths.items():
        source=path.read_text()
        assert "getFunctorByName<ADReal>" in source, name
        assert "_mass_fraction" in source, name
        assert "(r, state)" in source, name
    nv=(APP/"src/physics/plasma/NVTransport.C").read_text()
    assert 'fractions.emplace_back("Y_" + id)' in nv
    assert 'if (rootGasStateEnabled())' in nv


def test_metadata_is_not_inferred_for_a_flux_boundary():
    c=CODE.read_text()
    assert 'MooseEnum("none dirichlet", "none")' in c
    assert 'getParam<std::vector<BoundaryName>>("inlet_boundaries")' in c
    assert '"mass-flux inlets remain explicitly owned by their flow BCs."' in c
    assert 'if (getParam<MooseEnum>("inlet_bc_model") == "dirichlet")' in c


def test_all_four_materials_share_y_i_of_solver_state_in_native_fixture():
    data=json.loads((APP/"ci/json_species_live_all4_p2.json").read_text())
    source=(APP/"ci/json_species_live_all4_p2.i").read_text()
    assert abs(sum(v["initial_vol_mass_fraction"] for v in data["species"].values())-1.0)<1e-14
    assert abs(sum(v["initial_inlet_mass_fraction"] for v in data["species"].values())-1.0)<1e-14
    assert data["species"]["O2"]["initial_inlet_mass_fraction"] != data["species"]["O2"]["initial_vol_mass_fraction"]
    for id,record in data["species"].items():
        assert record["mass_fraction_variable"] == "w_"+id
        assert f"    functor = Y_{id}_initial_vol" not in source  # not a live state
        assert f"  [w_{id}]" in source
    for owner in ("HRateCoefMaterial","SurfaceReactionMaterial",
                  "PhysicsPlasmaChargeDensityMaterial"):
        assert owner in source
    # NVTransportMaterial is Physics-generated from the JSON transport record,
    # not explicitly named as a user-authored Material in the input file.
    assert "[NavierStokes]" in source
    assert "navier_stokes" in data["transport_coefficients"]
    assert (APP/"src/physics/plasma/NVTransport.C").read_text().count(
        'fractions.emplace_back("Y_" + id)') == 1
    for name in ("Y_O2", "Y_O", "Y_Op"):
        assert name in source
    assert "mass_fractions = 'Y_O2 Y_O Y_Op'" in source
    assert "ion_mass_fractions = 'Y_Op'" in source
    assert "active_reactions = 'H91'" in source
    assert "active_reactions = 'H90'" in source
    assert "inlet_bc_model = dirichlet" in source
    assert "initialize_species_mass_fractions = true" in source
