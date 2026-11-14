"""Two-model transport-coefficient ownership contract for Issue #402.

Exact-head Native compilation/P2 and physical result parity are separate gates.
Historical electron lookup aliases are retired; the separate NV thermal
alias is retired. Frozen source archives are not modified.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "physics_app/src/materials"
INC = ROOT / "physics_app/include/materials"


def test_dd_and_nv_canonical_materials_and_retired_implementations():
    for cls in ("DDTransportMaterial", "NVTransportMaterial"):
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
    dd = (SRC / "DDTransportMaterial.C").read_text()
    hd = (INC / "DDTransportMaterial.h").read_text()
    for token in ('"species_id"', '"model"', '"lookup constant functor"', '"table_file"',
                  '"mobility"', '"diffusivity"', '"table_units"', '"pressure"',
                  '"gas_temperature"'):
        assert token in dd
    for token in ('"ElectronTransportLookupMaterial"', '"PhysicsElectronTransportLookupMaterial"'):
        assert token not in dd  # removed factory aliases
    assert 'std::make_unique<PhysicsLookupTable1D>' in dd
    assert '_species + "_mobility"' in dd
    assert '_species + "_diffusivity"' in dd
    assert 'energy_factor = 5.0 / 3.0' in dd
    assert 'return _reduced ? raw / neutralNumberDensity(r, state) : raw;' in hd
    assert 'return pressure / (PHYSICS_CONSTANTS::k_boltz * T_g);' in hd
    assert '_constant_mobility < 0.0 || _constant_diffusivity < 0.0' in dd
    assert 'Mobility and diffusivity must be finite and nonnegative' in dd
    for removed in ('"property_table_file"', '"coordinate"', '"mean_energy"'):
        assert removed not in dd
    assert 'Lookup transport requires table_file.' in dd
    assert 'getFunctorByName<ADReal>("e_energy_eV")' in dd


def test_nv_retains_unmodified_collision_integral_and_mixture_model():
    nv = (SRC / "NVTransportMaterial.C").read_text()
    head = (INC / "NVTransportMaterial.h").read_text()
    assert "registerMooseObjectAliased(" not in nv
    for formula in ("debyeHuckelCollisionData", "interpolateCollisionIntegral",
                    "collisionData", "evaluateDmix", "D_mix", "D_T", "kT"):
        assert formula in nv or formula in head
    assert "DEBYE_TSTAR" in nv and "DEBYE_TABLE" in nv
    assert '"transport_data_file"' in nv
    assert '"mass_fractions"' in nv


def test_native_p2_input_exercises_both_new_models():
    inp = (ROOT / "physics_app/ci/dd_nv_material_smoke.i").read_text()
    assert inp.count("type = DDTransportMaterial") == 2
    assert inp.count("type = NVTransportMaterial") == 1
    assert "model = constant" in inp and "model = lookup" in inp
    assert "table_units = physical" in inp
    assert "mobility = 0.25" in inp and "diffusivity = 0.125" in inp
    runner = (ROOT / "experiments/Issue402_plasma_dsl_g1/run_native_binding_smoke.sh").read_text()
    assert 'native --check-input -i "physics_app/ci/dd_nv_material_smoke.i"' in runner
    assert "PLASMA_DD_NV_MATERIALS_P2_PASS" in runner


def test_redundant_composite_retired_but_needed_ion_functor_bridge_remains():
    inp = (ROOT / "physics_app/ci/plasma_direct_existing_materials_smoke.i").read_text()
    assert not (SRC / "ElectronClosureMaterial.C").exists()
    assert not (INC / "ElectronClosureMaterial.h").exists()
    assert "type = ElectronEnergyMaterial" in inp
    assert "type = DDTransportMaterial" in inp
    # Existing nonconstant heavy-ion coefficient Functors still require a
    # pass-through name bridge; replacing them by constants would alter physics.
    dd = (SRC / "DDTransportMaterial.C").read_text()
    header = (INC / "DDTransportMaterial.h").read_text()
    assert 'const bool explicit_mu = isParamValid("mobility_source")' in dd
    assert 'const bool explicit_D = isParamValid("diffusivity_source")' in dd
    assert '_species + "_mobility"' in dd
    assert '_species + "_diffusivity"' in dd
    assert 'getFunctorByName<ADReal>(mu)' in dd
    assert 'getFunctorByName<ADReal>(diffusion)' in dd
    assert 'getFunctor<ADReal>("mobility_source")' in dd
    assert 'getFunctor<ADReal>("diffusivity_source")' in dd
    assert 'return (*_mobility_source)(r, state);' in header
    assert 'return (*_diffusivity_source)(r, state);' in header
    assert not (SRC / "SpeciesTransportAliasMaterial.C").exists()
    assert not (INC / "SpeciesTransportAliasMaterial.h").exists()
