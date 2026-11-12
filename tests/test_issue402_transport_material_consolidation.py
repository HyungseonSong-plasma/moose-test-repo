"""Two-model transport-coefficient ownership contract for Issue #402.

Exact-head Native compilation/P2 and physical result parity are separate gates.
Historical model input aliases are intentionally accepted, but no duplicate
old C++ table/thermal implementations may survive.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "physics_app/src/materials"
INC = ROOT / "physics_app/include/materials"


def test_dd_and_nv_canonical_materials_and_retired_implementations():
    for cls in ("DDMaterial", "NVMaterial"):
        header, source = INC / f"{cls}.h", SRC / f"{cls}.C"
        assert header.is_file() and source.is_file()
        assert f"class {cls} : public FunctorMaterial" in header.read_text()
        assert f'registerMooseObject("PhysicsApp", {cls});' in source.read_text()
    for old in ("ElectronTransportLookupMaterial",
                "PhysicsThermalDiffusionMaterial",
                "PhysicsElectronTransportCoefficients"):
        assert not (INC / f"{old}.h").exists()
        assert not (SRC / f"{old}.C").exists()


def test_dd_constant_lookup_units_naming_and_energy_projection():
    dd = (SRC / "DDMaterial.C").read_text()
    hd = (INC / "DDMaterial.h").read_text()
    for token in ('"species_id"', '"model"', '"lookup constant"', '"table_file"',
                  '"mobility"', '"diffusivity"', '"table_units"', '"pressure"',
                  '"gas_temperature"'):
        assert token in dd
    for token in ('"ElectronTransportLookupMaterial"', '"PhysicsElectronTransportLookupMaterial"'):
        assert token in dd  # legacy factory input maps to one implementation
    assert 'std::make_unique<PhysicsLookupTable1D>' in dd
    assert '_species + "_mobility"' in dd
    assert '_species + "_diffusivity"' in dd
    assert 'energy_factor = 5.0 / 3.0' in dd
    assert 'return _reduced ? raw / neutralNumberDensity(r, state) : raw;' in hd
    assert 'return pressure / (PHYSICS_CONSTANTS::k_boltz * T_g);' in hd
    assert '_constant_mobility < 0.0 || _constant_diffusivity < 0.0' in dd
    assert 'Mobility and diffusivity must be finite and nonnegative' in dd
    assert 'Specify exactly one table_file or property_table_file' in dd
    assert 'Specify exactly one coordinate or mean_energy' in dd


def test_nv_retains_unmodified_collision_integral_and_mixture_model():
    nv = (SRC / "NVMaterial.C").read_text()
    head = (INC / "NVMaterial.h").read_text()
    assert 'registerMooseObjectAliased("PhysicsApp", NVMaterial, "PhysicsThermalDiffusionMaterial");' in nv
    for formula in ("debyeHuckelCollisionData", "interpolateCollisionIntegral",
                    "collisionData", "evaluateDmix", "D_mix", "D_T", "kT"):
        assert formula in nv or formula in head
    assert "DEBYE_TSTAR" in nv and "DEBYE_TABLE" in nv
    assert '"transport_data_file"' in nv
    assert '"mass_fractions"' in nv


def test_native_p2_input_exercises_both_new_models():
    inp = (ROOT / "physics_app/ci/dd_nv_material_smoke.i").read_text()
    assert inp.count("type = DDMaterial") == 2
    assert inp.count("type = NVMaterial") == 1
    assert "model = constant" in inp and "model = lookup" in inp
    assert "table_units = physical" in inp
    assert "mobility = 0.25" in inp and "diffusivity = 0.125" in inp
    runner = (ROOT / "experiments/Issue402_plasma_dsl_g1/run_native_binding_smoke.sh").read_text()
    assert 'native --check-input -i "physics_app/ci/dd_nv_material_smoke.i"' in runner
    assert "PLASMA_DD_NV_MATERIALS_P2_PASS" in runner


def test_legacy_composition_material_retained_only_for_current_dependent_inputs():
    # ElectronClosureMaterial couples normalized/physical state creation and a
    # table. Its pinned direct-existing-Material input still requires it.
    old = (SRC / "ElectronClosureMaterial.C").read_text()
    inp = (ROOT / "physics_app/ci/plasma_direct_existing_materials_smoke.i").read_text()
    assert 'registerMooseObject("PhysicsApp", ElectronClosureMaterial);' in old
    assert "type = ElectronClosureMaterial" in inp
    # SpeciesTransportAliasMaterial remains for ion coefficients provided by
    # existing live Functors that cannot be replaced by constants without drift.
    alias = (SRC / "SpeciesTransportAliasMaterial.C").read_text()
    assert "(*" not in alias or '"mobility_source"' in alias
    assert 'getFunctor<ADReal>("mobility_source")' in alias
