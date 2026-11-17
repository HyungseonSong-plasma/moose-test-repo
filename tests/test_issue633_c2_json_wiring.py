"""C2 JSON->PlasmasAction 3 wall, 3+9 FVBC and current static/negative controls.

All results here are P0 source/schema checks, NOT actual physics-opt runtime.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from ci.guards.issue633_c2_json_wiring import C2ContractError, validate, FACTOR

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "physics_app/ci/issue633_c2_wall_3ion_overlay.json"


def data():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def fail(change, error):
    sample = data()
    change(sample)
    with pytest.raises(C2ContractError, match=error):
        validate(sample)


def general(d):
    return d["boundaries"]["inlet outlet plasma_electrode plasma_metal plasma_right"]["bcs"]


def dielectric(d, side="cover"):
    return d["boundaries"]["plasma_" + side]["bcs"]


def test_exact_three_materials_and_twelve_bcs_contract():
    evidence = validate(data())
    assert evidence == {
        "ion_wall_materials": 3, "normal_fvbcs": 3,
        "dielectric_fvbcs": 9, "surface_current_consumers": 3,
        "runtime": "NOT_RUN",
    }
    d = data()
    assert general(d)["Om_wall"]["factor"] == FACTOR
    assert "factor" not in dielectric(d)["Om_cover_dielectric"]


@pytest.mark.parametrize("identity", ("O2p", "Om", "Op"))
def test_missing_material_fails(identity):
    fail(lambda d: d["species"][identity].pop("ion_wall"), "SELECTED_ION_WALL_OWNER_MISMATCH")


def test_unselected_or_duplicate_fvm_species_fails():
    with pytest.raises(C2ContractError, match="INVALID_SELECTED_SPECIES"):
        validate(data(), ("O2p", "O2p", "Op"))
    with pytest.raises(C2ContractError, match="INVALID_SELECTED_SPECIES"):
        validate(data(), ("O2p", "nonexistent"))


def test_swapped_density_and_mobility_fail():
    fail(lambda d: d["species"]["Om"]["ion_wall"].update(ion_number_density="O2p_number_density"),
         "WRONG_DENSITY_FUNCTOR_Om")
    fail(lambda d: d["species"]["Op"]["ion_wall"].update(mobility="Om_mobility"),
         "WRONG_MOBILITY_FUNCTOR_Op")


def test_wrong_charge_mass_and_potential_fail():
    fail(lambda d: d["species"]["Om"].update(charge_number=1), "WRONG_ION_CHARGE_Om")
    fail(lambda d: d["species"]["O2p"]["ion_wall"].update(molar_mass=0.016),
         "WRONG_WALL_MOLAR_MASS_O2p")
    fail(lambda d: d["species"]["Op"]["ion_wall"].update(potential="wrong_potential"),
         "WALL_POTENTIAL_MISMATCH_Op")


def test_unknown_wall_fields_or_missing_wall_parameters_fail():
    fail(lambda d: d["species"]["Om"]["ion_wall"].update(output_prefix="negative_"),
         "INVALID_ION_WALL_FIELDS_Om")
    fail(lambda d: d["species"]["O2p"]["ion_wall"].pop("sticking"),
         "INVALID_ION_WALL_FIELDS_O2p")


@pytest.mark.parametrize("key,value,error", [
    ("sticking", -1, "INVALID_STICKING"),
    ("sticking", 2, "INVALID_STICKING"),
    ("sticking", float("inf"), "INVALID_STICKING"),
    ("sticking", True, "INVALID_STICKING"),
    ("ion_temperature_eV", -0.1, "INVALID_ion_temperature_eV"),
    ("migration_gate_smoothing_width", float("nan"), "INVALID_migration_gate_smoothing_width"),
    ("use_element_gradient_for_potential", 1, "INVALID_GRADIENT_FLAG"),
])
def test_invalid_wall_physics_parameter_fails(key, value, error):
    fail(lambda d: d["species"]["O2p"]["ion_wall"].update({key: value}), error)


def test_missing_or_swapped_normal_boundary_fails():
    fail(lambda d: general(d).pop("O2p_wall"), "DUPLICATE_OR_MISSING_FVBC")
    fail(lambda d: general(d)["Om_wall"].update(functor="Op_wall_number_flux"),
         "WRONG_NEUMANN_TYPE_FLUX_FACTOR")
    fail(lambda d: general(d)["O2p_wall"].update(factor=-FACTOR),
         "WRONG_NEUMANN_TYPE_FLUX_FACTOR")
    fail(lambda d: general(d)["O2p_wall"].pop("factor"),
         "WRONG_NEUMANN_TYPE_FLUX_FACTOR")


def test_missing_extra_swapped_dielectric_fails():
    fail(lambda d: dielectric(d)["Om_cover_dielectric"].update(signed_number_flux="O2p_wall_number_flux"),
         "WRONG_DIELECTRIC_TYPE_OR_SIGNED_FLUX")
    fail(lambda d: dielectric(d)["Op_cover_dielectric"].update(factor=-FACTOR),
         "WRONG_DIELECTRIC_TYPE_OR_SIGNED_FLUX")
    fail(lambda d: dielectric(d, "wafer").pop("O2p_wafer_dielectric"),
         "DUPLICATE_OR_MISSING_FVBC")


def test_missing_or_overlap_sideset_group_fails():
    fail(lambda d: d["boundaries"].pop("plasma_focus_ring"),
         "MISSING_EXTRA_OR_OVERLAPPING_SIDESETS")
    fail(lambda d: d["boundaries"].update(plasma_unknown={"bcs": {}}),
         "MISSING_EXTRA_OR_OVERLAPPING_SIDESETS")


def test_surface_current_requires_electron_functor():
    fail(lambda d: d["ion_surface_current"].update(electron_wall_number_flux=""),
         "INVALID_SURFACE_CURRENT")
    fail(lambda d: d.pop("ion_surface_current"), "INVALID_SURFACE_CURRENT")
    fail(lambda d: d["ion_surface_current"].update(legacy_electron_wall="electron_wall_number_flux"),
         "INVALID_SURFACE_CURRENT")


def test_cpp_factory_generation_and_legacy_fem_path_stays_separate():
    src = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    header = (ROOT / "physics_app/include/physics/plasma/Chemistry.h").read_text()
    assert '#include "DDContinuityEq.h"' in src
    assert '_awh.getActions<Plasma::DDContinuityEq>()' in src
    assert 'getParam<std::vector<std::string>>("fvm_species")' in src
    assert 'species.ion_wall = parsed;' in src
    assert 'params.set<std::string>("species_id") = id;' in src
    assert '_problem->addFunctorMaterial(type, id + "_wall", params);' in src
    assert 'params.set<MooseFunctorName>("signed_number_flux") = bc.signed_number_flux;' in src
    assert 'params.set<Real>("factor") = bc.factor;' in src
    assert src.count('_problem->addFVBC(bc.type, name, params);') == 2
    assert '_problem->addBoundaryCondition(bc.type, name, params);' in src
    for side in ("cover", "wafer", "focus_ring"):
        assert f'"{side}"' in src
        assert f'{side}_net_surface_current_density' in FIXTURE.read_text() or \
               '"_net_surface_current_density"' in src
    assert '1.602176634e-19*(' in src
    assert '"ion_wall"' in src
    assert 'struct IonWallRecord' in header
    assert 'double factor = 0.0;' in header


def test_wall_and_dielectric_classes_are_registered_by_ion2_donor():
    wall = (ROOT / "physics_app/src/functormaterials/IonWallFluxMaterial.C").read_text()
    dielectric_bc = (ROOT / "physics_app/src/fvbcs/FVLogMolarDielectricFluxBC.C").read_text()
    assert 'registerMooseObject("PhysicsApp", IonWallFluxMaterial);' in wall
    assert 'registerMooseObject("PhysicsApp", FVLogMolarDielectricFluxBC);' in dielectric_bc
    assert 'return gamma_signed / PHYSICS_CONSTANTS::N_A;' in dielectric_bc
    assert 'species_id + "_wall_" + suffix' in wall
    # Unity translation units include the legacy and C2 material together.
    # Helper functions need unique linkage names; laws and factory identities stay unchanged.
    assert "namespace IonWallC2Detail" in wall
    for helper in ("isFaceArg", "outwardPositivePart", "outwardNormal", "faceElectricField"):
        assert "IonWallC2Detail::" + helper in wall
