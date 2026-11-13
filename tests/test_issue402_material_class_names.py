"""Active C++ Material naming, with obsolete electron factory aliases removed.

Historical immutable B/C decks are not modified. New Native inputs must use
DDTransportMaterial, table_file and the fixed e_energy_eV lookup axis.
"""
from pathlib import Path
import ast
import hashlib

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "physics_app"
MAPPINGS = (("PhysicsThermalDiffusionMaterial", "NVTransportMaterial"),)


def test_material_files_have_only_canonical_factory_registration():
    for old_name, new_name in MAPPINGS:
        h = BASE / "include/materials" / (new_name + ".h")
        c = BASE / "src/materials" / (new_name + ".C")
        assert h.is_file() and c.is_file()
        assert not (BASE / "include/materials" / (old_name + ".h")).exists()
        assert not (BASE / "src/materials" / (old_name + ".C")).exists()
        header, source = h.read_text(), c.read_text()
        assert f"class {new_name} : public FunctorMaterial" in header or (
            f"class {new_name}" in header
        )
        assert f"class {old_name}" not in header
        assert f'#include "{new_name}.h"' in source
        assert f'registerMooseObject("PhysicsApp", {new_name});' in source
        assert "registerMooseObjectAliased(" not in source
        assert f"{new_name}::validParams()" in source


def test_retired_plasma_closures_action_preserves_material_factories():
    assert not (BASE / "src/actions/PlasmaClosuresAction.C").exists()
    assert not (BASE / "include/actions/PlasmaClosuresAction.h").exists()
    app = (BASE / "src/base/PhysicsApp.C").read_text()
    assert "PlasmaClosuresAction" not in app
    assert "PlasmaClosures/*" not in app
    # Legacy combined electron lookup/state implementation is retired.
    assert not (BASE / "src/materials/ElectronClosureMaterial.C").exists()
    assert not (BASE / "include/materials/ElectronClosureMaterial.h").exists()
    assert "type = DDTransportMaterial" in (BASE / "ci/plasma_direct_existing_materials_smoke.i").read_text()


def test_only_ddmaterial_lookup_types_exercised_by_native_p2_controls():
    sample = (ROOT / "experiments/Issue402_plasma_dsl_g1/valid_generated_transport_options.i").read_text()
    assert "files = plasma_auto_constant.json" in sample
    assert "[FunctorMaterials]" not in sample
    generated = (ROOT / "experiments/Issue402_plasma_dsl_g1/plasma_auto_constant.json").read_text()
    assert '"model": "constant"' in generated
    script = (ROOT / "experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py").read_text()
    tree = ast.parse(script)
    overlay = next(ast.literal_eval(item.value) for item in tree.body
                   if isinstance(item, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "OVERLAY"
                           for target in item.targets))
    assert overlay.count("type = DDTransportMaterial") == 3
    assert overlay.count("model = functor") == 3
    assert hashlib.sha256(overlay.encode()).hexdigest() == (
        "edf3f8e8194927e93783d136066799d60df2673af9245d6d4b990fb7d267b513"
    )
    dd = (BASE / "src/materials/DDTransportMaterial.C").read_text()
    assert 'registerMooseObject("PhysicsApp", DDTransportMaterial);' in dd
    for obsolete in ("ElectronTransportLookupMaterial",
                     "PhysicsElectronTransportLookupMaterial",
                     '"property_table_file"', '"coordinate"', '"mean_energy"'):
        assert obsolete not in dd
    assert 'getFunctorByName<ADReal>("e_energy_eV")' in dd
    for fixture in ("electron_energy_transport_smoke.i",
                    "electron_energy_lookup_response_smoke.i",
                    "electron_energy_joule_smoke.i",
                    "electron_energy_real_qvt_inventory_smoke.i"):
        text = (BASE / "ci" / fixture).read_text()
        assert "type = DDTransportMaterial" in text
        assert "model = lookup" in text
        assert "table_file =" in text
        for obsolete in ("PhysicsElectronTransportLookupMaterial",
                         "property_table_file", "mean_energy ="):
            assert obsolete not in text
    assert not (BASE / "src/materials/PlasmaChargeTransportMaterial.C").exists()
    assert not (BASE / "include/materials/PlasmaChargeTransportMaterial.h").exists()
    assert (BASE / "src/materials/NVTransportMaterial.C").is_file()
    assert not (BASE / "src/materials/SpeciesTransportAliasMaterial.C").exists()
    assert not (BASE / "include/materials/SpeciesTransportAliasMaterial.h").exists()


def test_moose_physics_action_and_immutability_boundary_stay_separate():
    assert (BASE / "src/physics/plasma/DDContinuityEq.C").is_file()
    assert (BASE / "include/physics/plasma/DDContinuityEq.h").is_file()
    assert "SCIENCE_HOLD" in (
        ROOT / "experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py"
    ).read_text()
