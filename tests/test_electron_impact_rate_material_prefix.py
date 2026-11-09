"""Keep EI rate internal naming clean without changing registered MOOSE object."""
from pathlib import Path


def test_ei_rate_material_internal_name_and_registration():
    root = Path(__file__).resolve().parents[1]
    header = (root / "physics_app/include/materials/PhysicsElectronImpactRateMaterial.h").read_text()
    implementation = (root / "physics_app/src/materials/PhysicsElectronImpactRateMaterial.C").read_text()

    assert "class ElectronImpactRateMaterial : public FunctorMaterial" in header
    assert "ElectronImpactRateMaterial(const InputParameters & parameters);" in header
    assert "using PhysicsElectronImpactRateMaterial = ElectronImpactRateMaterial;" in header
    assert "class PhysicsElectronImpactRateMaterial : public FunctorMaterial" not in header

    registration = 'registerMooseObject("PhysicsApp", PhysicsElectronImpactRateMaterial);'
    assert implementation.count(registration) == 1
    assert "ElectronImpactRateMaterial::validParams()" in implementation
    assert "ElectronImpactRateMaterial::ElectronImpactRateMaterial(" in implementation
    assert "ElectronImpactRateMaterial::interpolateStrict(" in implementation
    assert "PhysicsElectronImpactRateMaterial::" not in implementation

    assert implementation.count('mooseError("ElectronImpactRateMaterial') == 3
    assert 'mooseError("PhysicsElectronImpactRateMaterial' not in implementation
    assert "return k_raw * (n_e / N_A) * c_target;" in implementation
    assert "strict Stage-4 policy forbids clamp/floor" in implementation
