"""Issue #402: removed charge-transport assembler and separated Poisson owners.

These are source-ownership guards, not numerical Poisson parity evidence.
FEM supports charge_source_functor via FunctorKernel, or legacy MatBodyForce.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"


def test_charge_transport_assembler_is_retired_without_removing_charge_source():
    assert not (APP / "src/materials/PlasmaChargeTransportMaterial.C").exists()
    assert not (APP / "include/materials/PlasmaChargeTransportMaterial.h").exists()
    source = (APP / "src/materials/PhysicsPlasmaChargeDensityMaterial.C").read_text()
    for name in ('"ion_number_density_" + id', '"charge_number_density"',
                 '"charge_density"', '"poisson_charge_source"'):
        assert name in source
    assert 'registerMooseObject("PhysicsApp", PhysicsPlasmaChargeDensityMaterial);' in source
    old_factory = (APP / "ci/check_plasma_closures_contract.py").read_text()
    assert '("PhysicsPlasmaChargeTransportMaterial", "PlasmaChargeTransportMaterial")' not in old_factory
    fixture = (PILOT / "charge_core_ddmaterial_owner_p2.i").read_text()
    assert fixture.count("type = DDMaterial") == 3
    assert "type = PhysicsPlasmaChargeDensityMaterial" in fixture
    assert "type = PlasmaChargeTransportMaterial" not in fixture
    assert "functor = poisson_charge_source" in fixture


def test_poisson_fem_functor_and_legacy_property_are_distinct_rhs_modes():
    eq = (APP / "src/physics/plasma/PoissonEq.C").read_text()
    charge = (APP / "src/materials/PhysicsPlasmaChargeDensityMaterial.C").read_text()
    assert 'params.addParam<MaterialPropertyName>(' in eq
    assert 'params.addParam<MooseFunctorName>(' in eq
    assert '"charge_source_material"' in eq
    assert '"charge_source_functor"' in eq
    assert 'params.set<MaterialPropertyName>("material_property")' in eq
    assert 'params.set<MooseFunctorName>("functor")' in eq
    assert 'params.set<bool>("functor_on_rhs") = true;' in eq
    assert 'getProblem().addKernel(type, name() + "_charge_source", params);' in eq
    assert 'const std::string type = "MatBodyForce";' in eq
    assert 'const std::string type = "FunctorKernel";' in eq
    assert 'if (!isParamValid("charge_source_material") &&' in eq
    assert 'isParamValid("charge_source_material") && isParamValid("charge_source_functor")' in eq
    assert 'addFunctorProperty<ADReal>(\n      "poisson_charge_source"' in charge
    assert "getProblem().addFunctorMaterial(" not in eq


def test_legacy_fv_poisson_source_is_wired_independently_of_old_assembler():
    legacy = (ROOT / "experiments/Issue1_reactor_o2plus_integration/"
              "self_consistent_2d/self_consistent_2d.i").read_text()
    assert "type = QPXPlasmaChargeDensityMaterial" in legacy
    assert "type = FVCoupledForce" in legacy
    assert "v = poisson_charge_source" in legacy
    source = (APP / "src/fvkernels/PhysicsFVElectrostaticDrift.C").read_text()
    assert "-_potential.gradient(centered_face, state)" in source
    assert "electric_field_magnitude" not in source
