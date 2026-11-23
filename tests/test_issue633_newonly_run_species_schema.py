"""Issue #633 final S6-417/941 unified new-only mechanism schema.

P0 contract and negative controls, not an actual S6 11-layer P2 PASS.
Archived Hybrid and original source JSON remain unchanged.
"""
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from ci.guards.issue633_c2_json_wiring import C2ContractError, validate

ROOT = Path(__file__).resolve().parents[1]
CHEM = ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry"
PILOT = CHEM.parent
CASES = ("417", "941")
NAMES = {"e", "O2", "O", "O2p", "Om", "Op", "O2a"}
COMMON = {
    "elements", "charge_number", "molar_mass", "temperature_eV",
    "sticking_coefficient", "initial_number_density", "transport_coef",
}
IONS = {"O2p", "Om", "Op"}
N_A = 6.02214076e23


def run_json(case):
    return json.loads((CHEM / f"unified_s6_{case}_newonly.json").read_text())


@pytest.mark.parametrize("case", CASES)
def test_actual_final_schema_is_one_complete_json_and_old_source_is_unchanged(case):
    new = run_json(case)
    old = json.loads((CHEM / f"unified_s6_{case}.json").read_text())
    assert set(new) == {"species", "equations", "reactions", "drift_diffusion_boundaries", "ion_surface_current"}
    assert set(new["species"]) == NAMES
    assert new["equations"] == old["equations"]
    assert new["reactions"] == old["reactions"]
    assert len(new["reactions"]) == 8
    assert len(new["equations"]) == 8
    assert {x["id"] for x in new["reactions"]} == set(new["equations"])
    assert set(new["drift_diffusion_boundaries"]) == {
        "inlet outlet", "plasma_electrode plasma_metal plasma_right",
        "plasma_cover", "plasma_wafer", "plasma_focus_ring",
    }
    assert validate(new) == {
        "ion_wall_materials": 3, "normal_fvbcs": 3, "dielectric_fvbcs": 9,
        "surface_current_consumers": 3, "runtime": "NOT_RUN",
    }


@pytest.mark.parametrize("case", CASES)
def test_all_seven_species_have_same_core_keys(case):
    species = run_json(case)["species"]
    for ident, entry in species.items():
        assert COMMON <= set(entry), ident
        assert entry["elements"] == (
            {} if ident == "e" else {"O": 2} if ident in {"O2", "O2p", "O2a"} else {"O": 1}
        )
        assert type(entry["charge_number"]) is int
        assert math.isfinite(entry["molar_mass"]) and entry["molar_mass"] > 0
        assert 0 <= entry["sticking_coefficient"] <= 1
        assert entry["temperature_eV"] is None or (
            math.isfinite(entry["temperature_eV"]) and entry["temperature_eV"] >= 0
        )
        assert entry["initial_number_density"] is None or (
            math.isfinite(entry["initial_number_density"]) and entry["initial_number_density"] > 0
        )
        assert {"type", "file", "unit"} <= set(entry["transport_coef"])
        assert "pressure" not in entry and "gas_temperature" not in entry
        for retired in ("wall_molar_mass", "wall_sticking", "wall_ion_temperature_eV",
                        "wall_use_element_gradient_for_potential",
                        "mobility", "diffusivity", "table_file", "table_units"):
            assert retired not in entry, (ident, retired)
    assert species["e"]["molar_mass"] == pytest.approx(5.485799096195737e-7)
    assert species["e"]["temperature_eV"] == pytest.approx(8 / 3)
    assert species["e"]["initial_number_density"] is not None
    assert "energy_transport_coef" not in species["e"]
    for ident in IONS:
        assert species[ident]["sticking_coefficient"] == 1
        assert species[ident]["temperature_eV"] is None  # existing T_g fallback
    assert species["e"]["sticking_coefficient"] == 1  # preserve electron sheath absorption
    for ident in {"O2", "O", "O2a"}:
        assert species[ident]["transport_coef"] == {
            "type": "none", "file": "none", "unit": "none"
        }


@pytest.mark.parametrize("case", CASES)
def test_typed_lookup_and_json_constant_ion_functors(case):
    species = run_json(case)["species"]
    electron = species["e"]["transport_coef"]
    assert electron["type"] == "lookup" and electron["unit"] == "reduced"
    assert electron["bounds_policy"] == "clamp"
    file = (CHEM / electron["file"]).resolve()
    assert file.is_file() and file.stat().st_size > 0
    for ident in IONS:
        assert species[ident]["transport_coef"] == {
            "type": "constant", "file": "none", "unit": "physical",
            "mobility": 10, "diffusivity": 0.25851999786435537
        }


@pytest.mark.parametrize("case", CASES)
def test_new_only_template_owns_pressure_temperature_potential_and_gate(case):
    deck = (PILOT / f"issue633_newonly_s6_{case}_continuity.template.i").read_text()
    assert f"files = 'chemistry/unified_s6_{case}_newonly.json'" in deck
    assert "issue633_c2_wall_3ion_overlay.json" not in deck
    assert "pressure = 1.333223684" in deck
    assert "temperature = 300" in deck
    assert "wall_gradient = adjacent_element" in deck
    assert "fem_potential = potential" in deck
    assert "fvm_species = 'O2p Om Op'" in deck
    assert "migration_smoothing_width = 0.001" in deck
    energy = deck.split("[Energy]", 1)[1].split("[]", 1)[0]
    assert "fem_species = e" in energy
    assert "fem_potential = potential" in energy
    assert "transport_coefficient = fluid" in energy
    assert "[Poisson]" not in deck


@pytest.mark.parametrize("case", CASES)
def test_modern_schema_negative_controls_are_fail_closed(case):
    original = run_json(case)
    cases = [
        (lambda d: d["species"]["e"].__setitem__("pressure", "p_fixed"),
         "RETIRED_SPECIES_FIELD_e_pressure"),
        (lambda d: d["species"]["e"].__setitem__("gas_temperature", "T_g_fixed"),
         "RETIRED_SPECIES_FIELD_e_gas_temperature"),
        (lambda d: d["species"]["O2p"]["transport_coef"].__setitem__("unit", "reduced"),
         "INVALID_CONSTANT_TRANSPORT_TEMPLATE_O2p"),
        (lambda d: d["species"]["O2p"].pop("sticking_coefficient"),
         "INCONSISTENT_COMMON_SPECIES_TEMPLATE"),
        (lambda d: d["species"]["Om"].__setitem__("wall_molar_mass", 0.016),
         "RETIRED_SPECIES_FIELD_Om_wall_molar_mass"),
        (lambda d: d["species"]["O2p"].__setitem__("temperature_eV", -1.0),
         "INVALID_TEMPERATURE_EV_O2p"),
        (lambda d: d["species"]["O2p"].__setitem__(
            "wall_use_element_gradient_for_potential", True),
         "WALL_GRADIENT_MUST_BE_PLASMAS_O2p"),
        (lambda d: d["species"]["O2p"]["transport_coef"].__setitem__("mobility", -1),
         "INVALID_CONSTANT_TRANSPORT_VALUE_O2p"),
        (lambda d: d["species"]["e"].__setitem__("energy_transport_coef", "fluid"),
         "ENERGY_TRANSPORT_SELECTOR_MUST_BE_MOOSE_INPUT"),
    ]
    for mutate, reason in cases:
        changed = deepcopy(original)
        mutate(changed)
        with pytest.raises(C2ContractError, match=reason):
            validate(changed)


def test_production_cpp_owner_for_typed_fields_and_electron_initial_temperature():
    chem = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    dd = (ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C").read_text()
    energy = (ROOT / "physics_app/src/physics/plasma/DDEnergyEq.C").read_text()
    for token in ('requiredText(entry, "type", file)', 'requiredText(entry, "file", file)',
                  'requiredText(entry, "unit", file)', 'result.mobility_source = id + "_mobility"',
                  'result.diffusivity_source = id + "_diffusivity"',
                  'result.root_owned_gas = unit == "reduced"',
                  'species.molar_mass = record.at("molar_mass").get<double>()',
                  'species.temperature_eV = temperature',
                  'wall.molar_mass = species.molar_mass',
                  'wall.sticking = species.sticking_coefficient'):
        assert token in chem, token
    assert 'rootGasStateEnabled()' in dd
    assert 'getActions<Plasma::DDEnergyEq>()' in dd
    assert 'getParam<MooseEnum>("transport_coefficient") == "fluid"' in dd
    assert 'getParam<MooseEnum>("transport_coefficient") != "fluid"' in energy
    assert 'energy_transport_coef is MOOSE [Energy] transport_coefficient-only' in chem
    assert 'params.set<Real>("mobility") = config->mobility;' in dd
    assert 'params.set<Real>("diffusivity") = config->diffusivity;' in dd
    assert 'const auto & electron = chemistryData().species("e")' in energy
    assert '1.5 * (*electron.temperature_eV) * (*electron.initial_number_density)' in energy
    assert 'params.set<Real>("value") = std::log(initial_energy)' in energy


@pytest.mark.parametrize("case", CASES)
def test_grouped_electron_fem_and_ion_fv_boundary_contract(case):
    data = run_json(case)
    groups = data["drift_diffusion_boundaries"]
    inlet = groups["inlet outlet"]
    wall = groups["plasma_electrode plasma_metal plasma_right"]
    assert len(inlet) == len(IONS) == 3
    assert len(wall) == len(IONS) + 2 == 5
    assert wall["e_wall"] == {"type": "FEMElectronSheathBC"}
    assert wall["e_energy_wall"] == {"type": "FEMElectronEnergySheathBC"}
    for ident in IONS:
        assert inlet[ident + "_wall"] == {"type": "FVFunctorNeumannBC"}
        assert wall[ident + "_wall"] == {"type": "FVFunctorNeumannBC"}
    for side in ("cover", "wafer", "focus_ring"):
        dielectric = groups["plasma_" + side]
        assert len(dielectric) == len(IONS) + 2 == 5
        assert dielectric["e_" + side + "_dielectric"] == {
            "type": "FEMElectronSheathBC"
        }
        assert dielectric["e_energy_" + side + "_dielectric"] == {
            "type": "FEMElectronEnergySheathBC"
        }
        for ident in IONS:
            assert dielectric[ident + "_" + side + "_dielectric"] == {
                "type": "FVLogMolarDielectricFluxBC"
            }
    declarations = [name for group in groups.values() for name in group]
    assert len(declarations) == 23  # 3 ion walls recur across disjoint groups
    assert len(set(declarations)) == 20  # precisely 12 FV + 8 electron FEM BC owners
    assert all(set(bc) == {"type"} for group in groups.values()
               for bc in group.values())
    assert data["ion_surface_current"]["electron_wall_number_flux"] == "e_wall_number_flux"


def test_new_parser_and_wall_migration_units_are_single_owner():
    chem = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    dd_energy = (ROOT / "physics_app/src/physics/plasma/DDEnergyEq.C").read_text()
    assert '"drift_diffusion_boundaries"' in chem
    assert 'bc["factor"] = -1.0 / 6.02214076e23;' in chem
    assert 'bc["wall_number_flux"] = "e_wall_number_flux";' in chem
    assert 'bc["signed_number_flux"] = species_id + "_wall_number_flux";' in chem
    assert 'getParam<MooseEnum>("wall_gradient") == "adjacent_element"' in chem
    assert 'params.addParam<MooseEnum>(\n      "wall_gradient"' in chem
    assert 'wall.set<std::string>("species_id") = "e";' in dd_energy
    assert 'wall.set<Real>("sticking") = chemistryData().species("e").sticking_coefficient;' in dd_energy
    assert 'merged_bcs.emplace(' in chem
    assert 'normalized_boundaries[joined]["bcs"][name] = owner.first;' in chem
    assert 'spec.size() != 1' in chem
    assert 'per-BC sidesets override' not in chem


@pytest.mark.parametrize("case", CASES)
def test_sidesets_field_is_retired_and_merging_is_strict(case):
    groups = run_json(case)["drift_diffusion_boundaries"]
    for label, values in groups.items():
        assert "sidesets" not in label
        for bc in values.values():
            assert "sidesets" not in bc

    bad = run_json(case)
    bad["drift_diffusion_boundaries"]["plasma_cover"]["e_cover_dielectric"][
        "sidesets"] = "plasma_cover"
    with pytest.raises(C2ContractError, match="MODERN_BOUNDARY_REDUNDANT_FIELD_OR_TYPE"):
        validate(bad)

    bad = run_json(case)
    bad["drift_diffusion_boundaries"]["inlet outlet"]["O2p_wall"]["type"] = (
        "FVLogMolarDielectricFluxBC"
    )
    with pytest.raises(C2ContractError, match="MODERN_BOUNDARY_REDUNDANT_FIELD_OR_TYPE"):
        validate(bad)


def test_native_electron_wall_and_energy_bcs_cover_all_three_dielectrics():
    native = (PILOT / "native/s6_c0_physics_base_no_d1.i").read_text()
    for side in ("cover", "wafer", "focus_ring"):
        assert f"[electron_{side}_dielectric]" in native
        assert f"[electron_energy_{side}]" in native
        assert f"boundary = 'plasma_{side}'" in native


def test_ion_fvm_newonly_workflow_cannot_reenter_retired_fem_or_timesteps():
    """New-only CI is an explicit P0 surface, never the old 150/200-step P3."""
    workflow = (ROOT / '.github/workflows/ion-fvm-hybrid-staged-dt.yml').read_text()
    assert 'Ion-FVM New-only S6 source P0' in workflow
    assert "variant: ['417', '941']" in workflow
    assert 'prepare_s6_run_input.py' in workflow
    assert 'prepare_s6_newonly.py' in workflow
    assert 'ION_FVM_NEWONLY_S6_' in workflow
    assert 'P1=NOT_RUN P2=NOT_RUN P3=NOT_RUN SCIENCE_HOLD' in workflow
    assert 'FEMElectronSheathBC' in workflow
    assert 'FEMElectronEnergySheathBC' in workflow
    assert 'retire_p4_duplicate_owners(' in workflow
    assert "'P2':'NOT_RUN'" in workflow
    for old in (
        'prepare_ion_fvm_hybrid_staged_dt.py',
        'prepare_ion_fvm_hybrid_contour.py',
        'prepare_full_fem_contour_mesh.py',
        'generate_contour_mesh.py',
        'TimeSequenceStepper',
        'expected_steps: 150',
        'expected_steps: 200',
        'timeout --signal=TERM',
        'physics-opt -i',
        'make -C physics_app',
    ):
        assert old not in workflow, f'RETIRED_ION_FVM_CALLER_REINTRODUCED: {old}'
