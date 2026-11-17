"""Issue #633 S6 electron/pressure owner transfer audit. P0 only; not P1/P2."""
import importlib.util
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
CHEM = PILOT / "chemistry"
PRE = ROOT / "ci/p1_ion_new_only_preflight.py"
spec = importlib.util.spec_from_file_location("issue633_owner_preflight", PRE)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)
N_A = 6.02214076e23


def archived_base():
    return (PILOT / "native/s6_c0_physics_base_no_d1.i").read_text()


def new_mechanism(case):
    return json.loads((CHEM / f"unified_s6_{case}_newonly.json").read_text())


def new_deck(case):
    return (PILOT / f"issue633_newonly_s6_{case}_continuity.template.i").read_text()


def check(case, *layers):
    files = {"migrated_continuity.i": new_deck(case)}
    files.update({f"scratch_{n}.i": value for n, value in enumerate(layers)})
    return preflight.inspect(files, new_mechanism(case), "new-only")


@pytest.mark.parametrize("case", ("417", "941"))
def test_new_only_energy_and_ion_wiring_has_a_clean_static_p0(case):
    result = check(case)
    assert result["status"] == "P0_STATIC_PASS_ONLY", result["errors"]
    deck = new_deck(case)
    energy = deck.split("[Energy]", 1)[1].split("[]", 1)[0]
    assert "fem_potential = potential" in energy
    assert "transport_coefficient = fluid" in energy
    assert "energy_transport_coef" not in new_mechanism(case)["species"]["e"]


@pytest.mark.parametrize("case", ("417", "941"))
def test_json_constant_ion_transport_matches_actual_native_species_values(case):
    old = archived_base()
    names = next(line.split("=", 1)[1].strip().strip("'").split()
                 for line in old.splitlines() if "prop_names = 'p_fixed" in line)
    values = next(line.split("=", 1)[1].strip().strip("'").split()
                  for line in old.splitlines() if "prop_values = '1.333223684" in line)
    legacy = dict(zip(names, map(float, values)))
    data = new_mechanism(case)["species"]
    for ident, mu, diff in (("O2p", "ion_mobility", "ion_diffusion"),
                            ("Om", "negative_ion_mobility", "negative_ion_diffusion"),
                            ("Op", "atomic_positive_ion_mobility",
                             "atomic_positive_ion_diffusion")):
        contract = data[ident]["transport_coef"]
        assert contract == {
            "type": "constant", "file": "none", "unit": "physical",
            "mobility": legacy[mu], "diffusivity": legacy[diff],
        }


@pytest.mark.parametrize("case", ("417", "941"))
def test_json_electron_ic_is_equivalent_to_pinned_s6_native_initial_energy(case):
    source = archived_base()
    assert "initial_condition = -20.216123548032986" in source
    assert "initial_condition = -18.829829186913098" in source
    e = new_mechanism(case)["species"]["e"]
    expected_log_e = math.log(e["initial_number_density"]) - math.log(N_A)
    expected_log_energy = math.log(
        1.5 * e["temperature_eV"] * e["initial_number_density"] / N_A
    )
    assert expected_log_e == pytest.approx(-20.216123548032986, abs=1e-10)
    assert expected_log_energy == pytest.approx(-18.829829186913098, abs=1e-10)


def test_original_s6_has_all_legacy_electron_and_pressure_owners():
    source = archived_base()
    assert "[p]" in source and "pressure = p" in source
    for name in ("log_ne", "log_energy", "ne_time", "energy_time",
                 "energy_transport", "energy_joule", "electron_transport",
                 "mean_energy", "electron_physical_density", "electron_wall_flux"):
        assert f"[{name}]" in source
    for name in ("electron_sheath", "electron_cover_dielectric",
                 "electron_wafer_dielectric", "electron_focus_ring_dielectric",
                 "electron_energy_sheath", "electron_energy_cover",
                 "electron_energy_wafer", "electron_energy_focus_ring"):
        assert f"[{name}]" in source
    assert "type = PhysicsLowerDSurfaceCurrent" in source
    assert "surface_current_density = cover_net_surface_current_density" in source


@pytest.mark.parametrize("old", ("log_ne", "log_energy", "p",
                                   "mean_en_solved", "electron_wall_number_flux"))
def test_old_s6_token_is_a_fail_closed_newonly_input(old):
    result = check("417", f"[FunctorMaterials]\n  [legacy]\n"
                  f"    type = ADGenericFunctorMaterial\n"
                  f"    prop_names = old_alias\n"
                  f"    prop_values = '{old}'\n  []\n[]\n")
    assert result["status"] == "FAIL"
    assert any(x.startswith("P1_RETIRED_S6_REFERENCE:" + old + ":")
               for x in result["errors"])


@pytest.mark.parametrize("name,typ,variable", [
    ("ne_time", "PhysicsFEMLogMolarTimeDerivative", "log_e"),
    ("energy_time", "PhysicsFEMLogMolarTimeDerivative", "log_e_energy"),
    ("energy_transport", "PhysicsFEMLogMolarDriftDiffusion", "log_e_energy"),
    ("energy_joule", "PhysicsFEMLogMolarElectronJouleHeating", "log_e_energy"),
])
def test_old_electron_kernel_rejected_after_full_energy(name, typ, variable):
    result = check("941", "[Kernels]\n"
                   f"  [{name}]\n    type = {typ}\n"
                   f"    variable = {variable}\n  []\n[]\n")
    assert "P1_FULL_ENERGY_NATIVE_ELECTRON_KERNEL_OWNERS_1" in result["errors"]


@pytest.mark.parametrize("name,typ", [
    ("electron_transport", "PhysicsElectronTransportLookupMaterial"),
    ("mean_energy", "PhysicsElectronMeanEnergyMaterial"),
    ("electron_physical_density", "ADParsedFunctorMaterial"),
    ("electron_wall_flux", "PhysicsElectronAdjacentSheathWallFluxMaterial"),
])
def test_duplicate_native_electron_functor_material_rejected(name, typ):
    result = check("417", "[FunctorMaterials]\n"
                   f"  [{name}]\n    type = {typ}\n  []\n[]\n")
    assert "P1_FULL_ENERGY_NATIVE_ELECTRON_MATERIAL_OWNERS_1" in result["errors"]


def test_native_electron_fem_boundary_must_be_retired():
    result = check("417", "[BCs]\n  [electron_wafer_dielectric]\n"
                   "    type = PhysicsFEMLogMolarElectronFieldLimitedFluxBC\n"
                   "    variable = log_e\n    boundary = plasma_wafer\n"
                   "  []\n[]\n")
    assert "P1_NATIVE_ELECTRON_FEM_BC_OWNER_PRESENT_1" in result["errors"]


def test_pressure_variable_migrates_to_canonical_name_without_double_ic():
    source = "[Variables]\n  [pressure]\n    type = INSFVPressureVariable\n"
    # Root Plasmas sets FVConstantIC on the solved pressure variable.
    duplicate = check("417", source + "    initial_condition = 1.333223684\n  []\n[]")
    assert "P1_DUPLICATE_ROOT_PRESSURE_IC:scratch_0.i" in duplicate["errors"]
    migrated = check("417", source + "    block = plasma\n  []\n[]")
    assert migrated["status"] == "P0_STATIC_PASS_ONLY", migrated["errors"]


def test_energy_physics_selector_is_required_and_json_is_not_owner():
    bad = new_deck("417").replace("          transport_coefficient = fluid\n", "")
    result = preflight.inspect({"migrated_continuity.i": bad}, new_mechanism("417"))
    assert "P1_ELECTRON_FLUID_TRANSPORT_SELECTOR_MISSING" in result["errors"]
