"""Issue 402: species-owned initial volume and inlet mixture contract.

These are source and analytic P0 checks. Native C++ parser rejection tests
and generated AD Functors are checked separately via the pinned MOOSE P2 job.
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
SOURCE = APP / "src/physics/plasma/Chemistry.C"
HEADER = APP / "include/physics/plasma/Chemistry.h"
FIXTURE = APP / "ci/json_surface_rate_p2.json"
INPUT = APP / "ci/json_surface_rate_p2.i"
AUDIT = APP / "ci/audit_issue402_initial_composition_routes.py"


def load_species():
    fixture = json.loads(FIXTURE.read_text())
    return fixture, fixture["species"]


def test_per_species_schema_and_no_top_level_gas_state():
    fixture, species = load_species()
    assert "gas_state" not in fixture
    assert "e" not in species
    assert set(species) == {"O2", "O"}
    assert species["O2"]["charge_number"] == 0
    assert species["O"]["charge_number"] == 0
    assert species["O2"]["initial_vol_mass_fraction"] == 0.9
    assert species["O2"]["initial_inlet_mass_fraction"] == 1.0
    assert species["O"]["initial_vol_mass_fraction"] == 0.1
    assert species["O"]["initial_inlet_mass_fraction"] == 0.0
    for prop in ("initial_vol_mass_fraction", "initial_inlet_mass_fraction"):
        assert math.isclose(sum(row[prop] for row in species.values()), 1.0, abs_tol=1e-15)


def test_cpp_parser_merges_and_validates_separate_species_fields():
    header = HEADER.read_text()
    source = SOURCE.read_text()
    assert "struct GasStateRecord" not in header
    assert "ChemistryData::gasState" not in source
    assert "parseGasState" not in source
    assert "std::optional<double> initial_vol_mass_fraction;" in header
    assert "std::optional<double> initial_inlet_mass_fraction;" in header
    for key in ("initial_vol_mass_fraction", "initial_inlet_mass_fraction"):
        assert f'"{key}"' in source
        assert f'existing->second.{key}' in source
    assert "top-level gas_state is retired" in source
    assert "electron 'e' cannot declare heavy mass fractions" in source
    assert "must declare both initial_vol_mass_fraction" in source
    assert "must be finite and within [0,1]" in source
    assert "requires molar_mass_kg_mol" in source


def test_volume_initial_and_inlet_values_have_different_roles():
    fixture, species = load_species()
    p, T, R = 1.333223684, 300.0, 8.31446261815324
    def rho(key):
        reciprocal_mass = sum(s[key] / s["molar_mass_kg_mol"] for s in species.values())
        return p / (R * T * reciprocal_mass)
    volume_density = rho("initial_vol_mass_fraction")
    inlet_density = rho("initial_inlet_mass_fraction")
    assert volume_density < inlet_density
    assert math.isclose(inlet_density, p * 0.032 / (R * T), rel_tol=1e-14)
    assert math.isclose(volume_density, p / (R * T * (0.9 / .032 + 0.1 / .016)), rel_tol=1e-14)


def test_generated_functors_are_distinct_from_evolving_solver_state():
    source = SOURCE.read_text()
    inp = INPUT.read_text()
    assert 'add("Y_" + id + "_initial_vol"' in source
    assert 'add("Y_" + id + "_inlet"' in source
    assert "if (!nv)" not in source
    assert 'fractions.push_back("Y_" + id)' in source
    assert 'add("Y_" + id, "live_y", {live}, {"live_y"});' in source
    assert "initialize_species_mass_fractions" in inp
    assert "inlet_bc_model = dirichlet" in inp
    assert "mass_fraction_variable" in source
    assert "mass_fraction_functor" in source
    assert "NV transport species to match the complete" in source
    assert "boundaries and flow ownership remain" in source
    assert "gas_state" not in inp
    assert "prop_names = 'Y_O2 Y_O'" not in inp
    assert "functor = Y_O2_initial_vol" in inp
    assert "functor = Y_O2_inlet" in inp
    assert "functor = Y_O_inlet" in inp
    assert "functor = rho_g_initial" in inp
    assert "functor = rho_g_inlet" in inp
    assert "functor = M_mix_inlet" in inp
    assert 'add("rho_g_inlet"' in source
    assert 'add("rho_g_initial"' in source


def test_repository_wide_inventory_is_executable_and_covers_owners():
    spec = importlib.util.spec_from_file_location("composition_routes", AUDIT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    inventory = module.audit()
    assert inventory["scanned_source_file_count"] > 350
    assert not inventory["retired_top_level_gas_state_json"]
    catalogue_paths = [x["path"] for x in inventory["species_initial_data_json"]]
    assert "physics_app/ci/json_surface_rate_p2.json" in catalogue_paths
    for category in (
        "species_schema_and_json", "bulk_initialization",
        "inlet_boundary_and_feed", "live_species_composition",
        "gas_eos_and_closure", "rate_transport_charge_consumers",
    ):
        assert inventory["matched_route_counts"][category] > 0
    paths = {entry["path"] for row in inventory["routes"].values() for entry in row}
    for path in (
        "physics_app/src/physics/plasma/Chemistry.C",
        "physics_app/src/materials/NVTransportMaterial.C",
        "physics_app/src/materials/HRateCoefMaterial.C",
        "physics_app/src/materials/SurfaceReactionMaterial.C",
        "physics_app/src/materials/PhysicsPlasmaChargeDensityMaterial.C",
        "physics_app/src/physics/plasma/DDContinuityEq.C",
    ):
        assert path in paths
