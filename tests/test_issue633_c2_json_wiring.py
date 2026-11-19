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
    fail(lambda d: [d["species"][identity].pop(key) for key in list(d["species"][identity])
                    if key.startswith("wall_")],
         "SELECTED_ION_WALL_OWNER_MISMATCH")


def test_unselected_or_duplicate_fvm_species_fails():
    with pytest.raises(C2ContractError, match="INVALID_SELECTED_SPECIES"):
        validate(data(), ("O2p", "O2p", "Op"))
    with pytest.raises(C2ContractError, match="INVALID_SELECTED_SPECIES"):
        validate(data(), ("O2p", "nonexistent"))


def test_density_and_mobility_wall_overrides_are_not_json_inputs():
    fail(lambda d: d["species"]["Om"].update(ion_number_density="O2p_number_density"),
         "REDUNDANT_WALL_SOURCE_FIELD_Om_ion_number_density")
    fail(lambda d: d["species"]["Op"].update(wall_mobility="Om_mobility"),
         "INVALID_ION_WALL_FIELDS_Op")


def test_wrong_charge_mass_and_redundant_potential_fail():
    fail(lambda d: d["species"]["Om"].update(charge_number=1), "WRONG_ION_CHARGE_Om")
    fail(lambda d: d["species"]["O2p"].update(wall_molar_mass=0.016),
         "WRONG_WALL_MOLAR_MASS_O2p")
    fail(lambda d: d["species"]["Op"].update(potential="wrong_potential"),
         "REDUNDANT_WALL_SOURCE_FIELD_Op_potential")


def test_unknown_wall_fields_or_missing_wall_parameters_fail():
    fail(lambda d: d["species"]["Om"].update(wall_output_prefix="negative_"),
         "INVALID_ION_WALL_FIELDS_Om")
    fail(lambda d: d["species"]["O2p"].pop("wall_sticking"),
         "INVALID_ION_WALL_FIELDS_O2p")
    fail(lambda d: d["species"]["Om"].update(ion_wall={"sticking": 1}),
         "RETIRED_ION_WALL_WRAPPER")
    fail(lambda d: d["species"]["Op"].update(gas_temperature="T_g_fixed"),
         "REDUNDANT_WALL_SOURCE_FIELD_Op_gas_temperature")


@pytest.mark.parametrize("key,value,error", [
    ("wall_sticking", -1, "INVALID_STICKING"),
    ("wall_sticking", 2, "INVALID_STICKING"),
    ("wall_sticking", float("inf"), "INVALID_STICKING"),
    ("wall_sticking", True, "INVALID_STICKING"),
    ("wall_ion_temperature_eV", -0.1, "INVALID_wall_ion_temperature_eV"),
    ("wall_use_element_gradient_for_potential", 1, "INVALID_GRADIENT_FLAG"),
])
def test_invalid_wall_physics_parameter_fails(key, value, error):
    fail(lambda d: d["species"]["O2p"].update({key: value}), error)


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
         "EMPTY_BC_GROUP")


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
    assert 'params.set<MooseFunctorName>("factor") = factor_value.str();' in src
    assert 'std::setprecision(std::numeric_limits<Real>::max_digits10)' in src
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
    # The duplicate legacy ion-wall Factory is retired. Distinct internal
    # symbols remain Unity-safe without a temporary C2 helper namespace.
    assert "namespace IonWallC2Detail" not in wall
    assert not (ROOT / "physics_app/src/functormaterials/PhysicsIonWallFluxMaterial.C").exists()
    for helper in ("ionWallIsFaceArg", "ionWallOutwardPositivePart",
                   "ionWallOutwardNormal", "ionWallFaceElectricField"):
        assert wall.count(helper) >= 2



def test_explicit_canonical_electron_wall_flux_is_allowed_only_when_named():
    stage = data()
    stage["ion_surface_current"]["electron_wall_number_flux"] = "e_wall_number_flux"
    assert validate(stage)["surface_current_consumers"] == 3
    fail(lambda d: d["ion_surface_current"].update(
        electron_wall_number_flux="unverified_flux_alias"),
        "INVALID_SURFACE_CURRENT_ELECTRON_CONSUMER")


def test_fem_electron_and_ion_fv_bcs_can_share_a_group():
    stage = data()
    dielectric(stage)["e_cover_sheath"] = {
        "type": "FEMElectronSheathBC",
        "variable": "log_e",
        "wall_number_flux": "electron_wall_number_flux",
    }
    assert validate(stage)["dielectric_fvbcs"] == 9
    stage["boundaries"]["left"] = {
        "bcs": {
            "e_left_sheath": {
                "type": "FEMElectronSheathBC",
                "variable": "log_e",
                "wall_number_flux": "electron_wall_number_flux",
            }
        }
    }
    assert validate(stage)["normal_fvbcs"] == 3
    stage["boundaries"]["left"]["bcs"]["bad_ion_on_left"] = {
        "type": "FVLogMolarDielectricFluxBC",
        "variable": "log_Op",
        "signed_number_flux": "Op_wall_number_flux",
    }
    with pytest.raises(C2ContractError, match="MISSING_EXTRA_OR_OVERLAPPING_SIDESETS"):
        validate(stage)


def test_extra_and_duplicate_ion_boundary_operators_fail():
    fail(lambda d: dielectric(d).update(O2p_duplicate={
        "type": "FVLogMolarDielectricFluxBC",
        "variable": "log_O2p",
        "signed_number_flux": "O2p_wall_number_flux",
    }), "DUPLICATE_BC_OPERATOR")
    fail(lambda d: general(d)["Om_wall"].update(type="PhysicsFVLogMolarDielectricFluxBC"),
         "UNSUPPORTED_FV_BC_TYPE")
    fail(lambda d: dielectric(d)["Op_cover_dielectric"].update(
        variable="log_O2p"), "DUPLICATE_BC_OPERATOR")


def test_electron_bc_duplicate_operator_and_bad_source_fail_closed():
    stage = data()
    electron = {
        "type": "FEMElectronSheathBC", "variable": "log_e",
        "wall_number_flux": "electron_wall_number_flux",
    }
    dielectric(stage)["e_cover_sheath"] = electron
    dielectric(stage)["e_cover_again"] = dict(electron)
    with pytest.raises(C2ContractError, match="DUPLICATE_BC_OPERATOR"):
        validate(stage)
    dielectric(stage).pop("e_cover_again")
    dielectric(stage)["e_cover_sheath"]["wall_number_flux"] = "e_wall_number_flux"
    with pytest.raises(C2ContractError, match="INVALID_EXISTING_FEM_ELECTRON_BC"):
        validate(stage)


def test_overlapping_sidesets_fail_even_across_separate_groups():
    stage = data()
    stage["boundaries"]["plasma_cover inlet"] = {
        "bcs": {
            "e_overlap": {
                "type": "FEMElectronSheathBC", "variable": "log_e",
                "wall_number_flux": "electron_wall_number_flux",
            }
        }
    }
    with pytest.raises(C2ContractError, match="MISSING_EXTRA_OR_OVERLAPPING_SIDESETS"):
        validate(stage)


def test_electron_and_density_producers_are_external_conditions_not_c2_fabrications():
    energy = (ROOT / "physics_app/src/physics/plasma/DDEnergyEq.C").read_text()
    chem = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    assert 'if (!sheath_wall)' in energy
    assert 'getProblem().addFunctorMaterial(wall_type, name() + "_sheath_wall_flux", wall)' in energy
    assert 'wall_type = "ESWallFluxMaterial"' in energy
    assert 'bc.wall_number_flux != "electron_wall_number_flux"' in energy
    # C2 checks explicit sources: ion_1/P09 and actual Scratch must prove
    # live O2p/Om/Op_number_density and selected electron wall source.
    assert 'params.set<MooseFunctorName>("ion_number_density") = id + "_number_density";' in chem
    assert 'params.set<MooseFunctorName>("potential") = potential;' in chem
    assert 'params.set<MooseFunctorName>("gas_temperature") = "temperature";' in chem
    assert 'continuity.front()->getParam<std::vector<SubdomainName>>("block")' in chem
    assert 'functors.push_back(_data.surfaceElectronWallFlux());' in chem
    assert "1.602176634e-19*(" in chem
    assert 'current_expression += "-ge";' in chem
    assert 'const std::string flux = id + "_wall_number_flux";' in chem
    assert 'bc.signed_number_flux != flux' in chem



def test_existing_electron_energy_sheath_can_share_dielectric_side():
    stage = data()
    dielectric(stage)["electron_cover"] = {
        "type": "FEMElectronSheathBC",
        "variable": "log_e",
        "wall_number_flux": "electron_wall_number_flux",
    }
    dielectric(stage)["electron_energy_cover"] = {
        "type": "FEMElectronEnergySheathBC",
        "variable": "log_e_energy",
        "wall_number_flux": "electron_wall_number_flux",
        "mean_energy": "e_energy_eV",
    }
    assert validate(stage)["dielectric_fvbcs"] == 9
    dielectric(stage)["electron_energy_cover"]["variable"] = "log_e"
    with pytest.raises(C2ContractError, match="INVALID_EXISTING_FEM_ELECTRON_BC"):
        validate(stage)


@pytest.mark.parametrize("field,value", [
    ("type", []), ("type", {}), ("type", None), ("variable", None)
])
def test_malformed_boundary_type_and_variable_fail_as_contract_error(field, value):
    stage = data()
    general(stage)["O2p_wall"][field] = value
    with pytest.raises(C2ContractError):
        validate(stage)


def test_non_string_electron_current_selection_fails_closed():
    for invalid in (["electron_wall_number_flux"], None, 17):
        stage = data()
        stage["ion_surface_current"]["electron_wall_number_flux"] = invalid
        with pytest.raises(C2ContractError, match="INVALID_SURFACE_CURRENT_ELECTRON_CONSUMER"):
            validate(stage)



def test_general_wall_group_permutation_preserves_same_five_physical_sidesets():
    stage = data()
    old = "inlet outlet plasma_electrode plasma_metal plasma_right"
    new = "plasma_right plasma_metal inlet outlet plasma_electrode"
    stage["boundaries"][new] = stage["boundaries"].pop(old)
    assert validate(stage)["normal_fvbcs"] == 3


def test_cpp_charge_guard_preserves_signed_s6_three_ion_ledger():
    source = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    assert 'const int expected_charge = id == "Om" ? -1 : 1;' in source
    assert 'if (_data.species(id).charge_number != expected_charge)' in source
    assert 'current_expression += "-ge";' in source


def test_flat_species_wall_schema_uses_one_moose_temperature_and_potential_owner():
    overlay = data()
    for id in ("O2p", "Om", "Op"):
        record = overlay["species"][id]
        assert "ion_wall" not in record
        assert set(key for key in record if key.startswith("wall_")) == {
            "wall_molar_mass", "wall_sticking", "wall_ion_temperature_eV",
            "wall_use_element_gradient_for_potential",
        }
        assert not any(key in record for key in
                       ("potential", "gas_temperature", "ion_number_density", "block"))
    source = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    assert 'if (!gasStateEnabled())' in source
    assert 'params.set<MooseFunctorName>("potential") = potential;' in source
    assert 'params.set<MooseFunctorName>("gas_temperature") = "temperature";' in source
    assert 'params.set<std::vector<SubdomainName>>("block") = blocks;' in source
    assert 'continuity.front()->getParam<Real>("migration_smoothing_width")' in source
    continuity = (ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C").read_text()
    assert 'params.addParam<Real>(\n      "migration_smoothing_width",\n      0.0,' in continuity
    assert 'getParam<Real>("migration_smoothing_width")' in continuity
    assert 'if (!isParamValid("migration_smoothing_width"))' not in continuity
    assert 'if (!std::isfinite(smoothing) || smoothing < 0.0)' in continuity


def test_smoothing_width_json_is_rejected_and_moose_input_is_sole_owner():
    for key in ("migration_smoothing_width", "wall_migration_gate_smoothing_width"):
        for value in (0.001, 0.0, -0.1, float("nan"), "0.001"):
            fail(lambda d: d["species"]["O2p"].update({key: value}),
                 "WALL_SMOOTHING_MUST_BE_MOOSE_INPUT_O2p")
        fail(lambda d: d.update({key: 0.001}),
             "WALL_SMOOTHING_MUST_BE_MOOSE_INPUT_ROOT")
    assert all(not any(key in sp for key in (
        "migration_smoothing_width", "wall_migration_gate_smoothing_width"))
        for sp in data()["species"].values())
    continuity = (ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C").read_text()
    parser = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    assert "migration_smoothing_width is MOOSE [Continuity]-only" in parser
    assert 'getParam<Real>("migration_smoothing_width")' in parser
    assert 'if (!isParamValid("migration_smoothing_width"))' not in continuity
    assert 'if (!std::isfinite(smoothing) || smoothing < 0.0)' in continuity
