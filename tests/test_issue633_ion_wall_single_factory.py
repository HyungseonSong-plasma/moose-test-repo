"""Single IonWallFluxMaterial registration and historical scratch migration.

A maintained runtime source may construct only IonWallFluxMaterial. Archived
S6 inputs retain their original factory spellings, but only as *input* to
fail-closed scratch canonicalization; no compatibility Factory is registered.
Source-level tests; native compilation and Warehouse remain independent gates.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "physics_app/src/functormaterials"
INC = ROOT / "physics_app/include/functormaterials"
ACTION = ROOT / "physics_app/src/physics/plasma/Chemistry.C"
CANON = (ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/"
         "prepare_s6_run_input.py")


def test_one_registered_ion_wall_implementation_and_unity_safe_helpers():
    new_cpp = SRC / "IonWallFluxMaterial.C"
    new_hdr = INC / "IonWallFluxMaterial.h"
    assert new_cpp.is_file() and new_hdr.is_file()
    assert not (SRC / "PhysicsIonWallFluxMaterial.C").exists()
    assert not (INC / "PhysicsIonWallFluxMaterial.h").exists()

    source = new_cpp.read_text(encoding="utf-8")
    assert source.count('registerMooseObject("PhysicsApp", IonWallFluxMaterial);') == 1
    assert "IonWallC2Detail" not in source
    assert "PhysicsIonWallFluxMaterial" not in source
    # Distinct helper symbols make Unity compilation safe without a second
    # physics implementation or an ad-hoc C2-only helper namespace.
    for helper in ("ionWallIsFaceArg", "ionWallOutwardNormal",
                   "ionWallFaceElectricField", "ionWallOutwardPositivePart"):
        assert source.count(helper) >= 2
    for root in (ROOT / "physics_app/src", ROOT / "physics_app/include"):
        for file in root.rglob("*"):
            if file.suffix in {".C", ".h"}:
                assert "PhysicsIonWallFluxMaterial" not in file.read_text(encoding="utf-8"), file

    chemistry = ACTION.read_text(encoding="utf-8")
    assert 'const auto type = "IonWallFluxMaterial";' in chemistry
    assert '_factory.getValidParams(type);' in chemistry
    assert 'registerMooseObject("PhysicsApp", IonWallFluxMaterial);' in source
    assert 'class IonWallFluxMaterial : public FunctorMaterial' in new_hdr.read_text(encoding="utf-8")


def test_old_immutable_archive_input_maps_to_new_registered_class():
    spec = importlib.util.spec_from_file_location("issue633_wall_migration", CANON)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    historical = """[FunctorMaterials]
  [ion_wall_flux]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = n_i_physical
    potential = potential
    mobility = O2p_mobility
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.032
    sticking = 1
  []
[]
"""
    original = {Path("legacy_input.i"): historical}
    converted, receipt = module.canonicalize_staged_wall_inputs(original)
    assert original[Path("legacy_input.i")] == historical
    source = converted[Path("legacy_input.i")]
    assert "type = IonWallFluxMaterial" in source
    assert "type = PhysicsIonWallFluxMaterial" not in source
    assert "species_id = O2p" in source
    assert receipt["owner_count"] == 1
    assert receipt["wall_material_owners"][0]["source_type"] == "PhysicsIonWallFluxMaterial"
    assert receipt["wall_material_owners"][0]["type"] == "IonWallFluxMaterial"
    assert receipt["P3"] == "NOT_RUN" and receipt["science"] == "SCIENCE_HOLD"


def test_active_named_wall_factory_fixture_is_canonical():
    smoke = (ROOT / "physics_app/ci/species_wall_functor_naming_smoke.i").read_text()
    assert smoke.count("type = IonWallFluxMaterial") == 3
    assert "type = PhysicsIonWallFluxMaterial" not in smoke
    for name in ("O2p", "Op", "Om"):
        assert "species_id = " + name in smoke
        assert "ion_number_density = " + name + "_number_density" in smoke
