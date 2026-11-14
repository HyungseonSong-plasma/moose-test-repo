"""Issue402: only the three canonical Material C++ classes and factory tokens exist."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
RENAMED = {
    "ElectronImpactRateMaterial": "EIRateCoefMaterial",
    "DDMaterial": "DDTransportMaterial",
    "NVMaterial": "NVTransportMaterial",
}


def test_no_legacy_factory_alias_or_duplicate_implementation():
    for old, new in RENAMED.items():
        assert not (APP / "include/materials" / (old + ".h")).exists()
        assert not (APP / "src/materials" / (old + ".C")).exists()
        header = (APP / "include/materials" / (new + ".h")).read_text()
        source = (APP / "src/materials" / (new + ".C")).read_text()
        assert f"class {new} : public FunctorMaterial" in header
        assert f'#include "{new}.h"' in source
        assert source.count(f'registerMooseObject("PhysicsApp", {new});') == 1
        assert "registerMooseObjectAliased(" not in source
        assert f"{old}::" not in source
        assert f"{new}::validParams()" in source
    for old in ("PhysicsElectronImpactRateMaterial", "PhysicsThermalDiffusionMaterial"):
        assert not (APP / "include/materials" / (old + ".h")).exists()
        assert not (APP / "src/materials" / (old + ".C")).exists()


def test_generated_json_materials_use_canonical_type_tokens():
    dd = (APP / "src/physics/plasma/DDContinuityEq.C").read_text()
    nv = (APP / "src/physics/plasma/NVTransport.C").read_text()
    assert 'const std::string type = "DDTransportMaterial";' in dd
    assert 'const std::string type = "NVTransportMaterial";' in nv
    for old in ("DDMaterial", "NVMaterial", "ElectronImpactRateMaterial"):
        assert not re.search(r'const std::string type = "' + re.escape(old) + r'"', dd + nv)


def test_direct_checked_in_p2_inputs_only_use_canonical_material_types():
    inputs = (
        APP / "ci/dd_nv_material_smoke.i",
        APP / "ci/plasma_direct_existing_materials_smoke.i",
        APP / "ci/electron_energy_transport_smoke.i",
    )
    for path in inputs:
        content = path.read_text()
        for old in ("DDMaterial", "NVMaterial", "ElectronImpactRateMaterial",
                    "PhysicsElectronImpactRateMaterial", "PhysicsThermalDiffusionMaterial"):
            assert not re.search(r'(?m)^\s*type\s*=\s*' + re.escape(old) + r'\s*$', content)
    assert "type = DDTransportMaterial" in inputs[0].read_text()
    assert "type = NVTransportMaterial" in inputs[0].read_text()
    assert "type = EIRateCoefMaterial" in inputs[1].read_text()


def test_frozen_s6_source_is_remapped_only_after_staging():
    source = (ROOT / "experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py").read_text()
    for old, new in {
        "DDMaterial": "DDTransportMaterial",
        "NVMaterial": "NVTransportMaterial",
        "PhysicsThermalDiffusionMaterial": "NVTransportMaterial",
        "ElectronImpactRateMaterial": "EIRateCoefMaterial",
        "PhysicsElectronImpactRateMaterial": "EIRateCoefMaterial",
    }.items():
        assert f'"{old}": "{new}"' in source
