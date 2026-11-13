"""Canonical ElectronImpactRateMaterial class/file registration and legacy input compatibility."""
from pathlib import Path


def test_ei_rate_material_class_file_and_registration():
    root = Path(__file__).resolve().parents[1]
    app = root / "physics_app"
    header = (app / "include/materials/ElectronImpactRateMaterial.h").read_text()
    implementation = (app / "src/materials/ElectronImpactRateMaterial.C").read_text()

    assert not (app / "include/materials/PhysicsElectronImpactRateMaterial.h").exists()
    assert not (app / "src/materials/PhysicsElectronImpactRateMaterial.C").exists()
    assert "class ElectronImpactRateMaterial : public FunctorMaterial" in header
    assert "ElectronImpactRateMaterial(const InputParameters & parameters);" in header
    assert "using PhysicsElectronImpactRateMaterial = " not in header
    assert "class PhysicsElectronImpactRateMaterial" not in header
    assert '#include "ElectronImpactRateMaterial.h"' in implementation

    canonical = 'registerMooseObject("PhysicsApp", ElectronImpactRateMaterial);'
    legacy = 'registerMooseObjectAliased("PhysicsApp", ElectronImpactRateMaterial, "PhysicsElectronImpactRateMaterial");'
    assert implementation.count(canonical) == 1
    assert implementation.count(legacy) == 1
    assert "ElectronImpactRateMaterial::validParams()" in implementation
    assert "ElectronImpactRateMaterial::ElectronImpactRateMaterial(" in implementation
    assert "ElectronImpactRateMaterial::interpolateStrict(" in implementation
    assert "PhysicsElectronImpactRateMaterial::" not in implementation

    assert implementation.count('mooseError("ElectronImpactRateMaterial') == 3
    assert 'mooseError("PhysicsElectronImpactRateMaterial' not in implementation
    assert "return k_raw * (n_e / N_A) * c_target;" in implementation
    assert "strict Stage-4 policy forbids clamp/floor" in implementation
