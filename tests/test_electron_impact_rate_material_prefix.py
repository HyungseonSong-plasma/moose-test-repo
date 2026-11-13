"""Canonical EIRateCoefMaterial registration without any factory or C++ aliases."""
from pathlib import Path


def test_canonical_rate_coeff_material_no_legacy_registration():
    root = Path(__file__).resolve().parents[1]
    app = root / "physics_app"
    header = (app / "include/materials/EIRateCoefMaterial.h").read_text()
    source = (app / "src/materials/EIRateCoefMaterial.C").read_text()
    for old in ("ElectronImpactRateMaterial", "PhysicsElectronImpactRateMaterial"):
        assert not (app / "include/materials" / (old + ".h")).exists()
        assert not (app / "src/materials" / (old + ".C")).exists()
    assert "class EIRateCoefMaterial : public FunctorMaterial" in header
    assert "EIRateCoefMaterial(const InputParameters & parameters);" in header
    assert '#include "EIRateCoefMaterial.h"' in source
    assert source.count('registerMooseObject("PhysicsApp", EIRateCoefMaterial);') == 1
    assert 'registerMooseObjectAliased(' not in source
    assert "EIRateCoefMaterial::validParams()" in source
    assert "EIRateCoefMaterial::EIRateCoefMaterial(" in source
    assert "EIRateCoefMaterial::interpolateStrict(" in source
    assert source.count('mooseError("EIRateCoefMaterial') == 3
    assert "return k_raw * (n_e / N_A) * c_target;" in source
    assert "strict Stage-4 policy forbids clamp/floor" in source
