"""Canonical RateCoeffMaterial registration without any factory or C++ aliases."""
from pathlib import Path


def test_canonical_rate_coeff_material_no_legacy_registration():
    root = Path(__file__).resolve().parents[1]
    app = root / "physics_app"
    header = (app / "include/materials/RateCoeffMaterial.h").read_text()
    source = (app / "src/materials/RateCoeffMaterial.C").read_text()
    for old in ("ElectronImpactRateMaterial", "PhysicsElectronImpactRateMaterial"):
        assert not (app / "include/materials" / (old + ".h")).exists()
        assert not (app / "src/materials" / (old + ".C")).exists()
    assert "class RateCoeffMaterial : public FunctorMaterial" in header
    assert "RateCoeffMaterial(const InputParameters & parameters);" in header
    assert '#include "RateCoeffMaterial.h"' in source
    assert source.count('registerMooseObject("PhysicsApp", RateCoeffMaterial);') == 1
    assert 'registerMooseObjectAliased(' not in source
    assert "RateCoeffMaterial::validParams()" in source
    assert "RateCoeffMaterial::RateCoeffMaterial(" in source
    assert "RateCoeffMaterial::interpolateStrict(" in source
    assert source.count('mooseError("RateCoeffMaterial') == 3
    assert "return k_raw * (n_e / N_A) * c_target;" in source
    assert "strict Stage-4 policy forbids clamp/floor" in source
