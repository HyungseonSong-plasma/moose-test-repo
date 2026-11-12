"""C++ Material naming and legacy MOOSE factory input compatibility.

Old input type aliases are deliberately still used by archived P3 B/C inputs
and the small synthetic positive smoke; new D-only overlay uses canonical name.
Static tests complement exact-head Native --check-input execution in CI.
"""
from pathlib import Path
import ast
import hashlib

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "physics_app"
MAPPINGS = (
    ("PhysicsElectronClosureMaterial", "ElectronClosureMaterial"),
    ("PhysicsElectronTransportLookupMaterial", "ElectronTransportLookupMaterial"),
    ("PhysicsPlasmaChargeTransportMaterial", "PlasmaChargeTransportMaterial"),
    ("PhysicsSpeciesTransportAliasMaterial", "SpeciesTransportAliasMaterial"),
)


def test_canonical_files_and_classes_with_legacy_factory_aliases():
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
        assert (
            f'registerMooseObjectAliased("PhysicsApp", '
            f'{new_name}, "{old_name}");'
        ) in source
        assert f"{new_name}::validParams()" in source


def test_retired_plasma_closures_action_preserves_material_factories():
    assert not (BASE / "src/actions/PlasmaClosuresAction.C").exists()
    assert not (BASE / "include/actions/PlasmaClosuresAction.h").exists()
    app = (BASE / "src/base/PhysicsApp.C").read_text()
    assert "PlasmaClosuresAction" not in app
    assert "PlasmaClosures/*" not in app
    # ElectronClosureMaterial and its old Factory alias remain independently registered.
    closure = (BASE / "src/materials/ElectronClosureMaterial.C").read_text()
    assert 'registerMooseObject("PhysicsApp", ElectronClosureMaterial);' in closure
    assert 'registerMooseObjectAliased("PhysicsApp", ElectronClosureMaterial, "PhysicsElectronClosureMaterial");' in closure


def test_both_old_and_new_alias_types_exercised_by_native_p2_controls():
    sample = (ROOT / "experiments/Issue402_plasma_dsl_g1/valid_generated_transport_options.i").read_text()
    assert "type = PhysicsSpeciesTransportAliasMaterial" in sample
    script = (ROOT / "experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py").read_text()
    tree = ast.parse(script)
    overlay = next(ast.literal_eval(item.value) for item in tree.body
                   if isinstance(item, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "OVERLAY"
                           for target in item.targets))
    assert overlay.count("type = SpeciesTransportAliasMaterial") == 3
    assert "type = PhysicsSpeciesTransportAliasMaterial" not in overlay
    assert hashlib.sha256(overlay.encode()).hexdigest() == (
        "14288d9f0686f26cde86888824babc468016ece99188114ded31b8e5bd360d9a"
    )
    old_lookup = (BASE / "ci/electron_energy_transport_smoke.i").read_text()
    new_lookup = (BASE / "ci/electron_energy_lookup_response_smoke.i").read_text()
    assert "type = PhysicsElectronTransportLookupMaterial" in old_lookup
    assert "type = ElectronTransportLookupMaterial" in new_lookup


def test_moose_physics_action_and_immutability_boundary_stay_separate():
    assert (BASE / "src/physics/plasma/DDContinuityEq.C").is_file()
    assert (BASE / "include/physics/plasma/DDContinuityEq.h").is_file()
    assert "SCIENCE_HOLD" in (
        ROOT / "experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py"
    ).read_text()
