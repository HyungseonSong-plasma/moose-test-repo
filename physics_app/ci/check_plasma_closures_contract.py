#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

required = [
    ROOT / "include/actions/PlasmaClosuresAction.h",
    ROOT / "src/actions/PlasmaClosuresAction.C",
    ROOT / "include/materials/PhysicsElectronClosureMaterial.h",
    ROOT / "src/materials/PhysicsElectronClosureMaterial.C",
    ROOT / "include/materials/PhysicsElectronKineticsMaterial.h",
    ROOT / "src/materials/PhysicsElectronKineticsMaterial.C",
    ROOT / "include/materials/PhysicsHeavyTransportMaterial.h",
    ROOT / "src/materials/PhysicsHeavyTransportMaterial.C",
    ROOT / "include/materials/PhysicsPlasmaChargeDensityMaterial.h",
    ROOT / "src/materials/PhysicsPlasmaChargeDensityMaterial.C",
]
for path in required:
    assert path.is_file(), path

action = (ROOT / "src/actions/PlasmaClosuresAction.C").read_text()
header = (ROOT / "include/actions/PlasmaClosuresAction.h").read_text()
app = (ROOT / "src/base/PhysicsApp.C").read_text()
role_smoke = (ROOT / "ci/plasma_closures_smoke.i").read_text()
legacy_smoke = (ROOT / "ci/plasma_closures_legacy_api_smoke.i").read_text()
electron = (ROOT / "src/materials/PhysicsElectronClosureMaterial.C").read_text()
kinetics = (ROOT / "src/materials/PhysicsElectronKineticsMaterial.C").read_text()
heavy = (ROOT / "src/materials/PhysicsHeavyTransportMaterial.C").read_text()

assert 'registerMooseAction("PhysicsApp", PlasmaClosuresAction, "add_functor_material")' in action
assert 'syntax.registerActionSyntax("PlasmaClosuresAction", "PlasmaClosures/*")' in app

# Role-based user API plus legacy custom/boolean compatibility.
assert 'MooseEnum("custom electron heavy_transport electrostatic_charge", "custom")' in action
for helper in (
    "electronClosureEnabled",
    "electronKineticsEnabled",
    "heavyTransportEnabled",
    "chargeDensityEnabled",
):
    assert helper in header
    assert helper in action

assert "role = electron" in role_smoke
assert "role = heavy_transport" in role_smoke
assert "role = electrostatic_charge" in role_smoke
assert "create_electron_closure" not in role_smoke
assert "create_electron_closure = true" in legacy_smoke
assert "create_heavy_transport = true" in legacy_smoke
assert "create_charge_density = true" in legacy_smoke

# The user-facing action composes four closures; it does not implement their physics.
for object_type in (
    "PhysicsElectronClosureMaterial",
    "PhysicsElectronKineticsMaterial",
    "PhysicsHeavyTransportMaterial",
    "PhysicsPlasmaChargeDensityMaterial",
):
    assert object_type in action

# Electron mean energy and transport are now owned by one material.
assert "electron_mean_energy_output" in electron
assert "electron_mobility_output" in electron
assert "electron_energy_diffusion_output" in electron

# Kinetics owns a reaction vector rather than one object per reaction.
assert "rate_table_files" in kinetics
assert "reaction_progress_names" in kinetics
assert "std::vector<PhysicsLookupTable1D>" in (
    ROOT / "include/materials/PhysicsElectronKineticsMaterial.h"
).read_text()

# Heavy transport reuses the already-qualified multi-species implementation.
assert "PhysicsThermalDiffusionMaterial" in heavy

# Backward compatibility: legacy material implementations remain present.
for legacy in (
    "PhysicsElectronMeanEnergyMaterial.C",
    "PhysicsElectronTransportLookupMaterial.C",
    "PhysicsElectronImpactRateMaterial.C",
    "PhysicsThermalDiffusionMaterial.C",
):
    assert (ROOT / "src/materials" / legacy).is_file(), legacy

print("PLASMA_CLOSURES_CONTRACT: PASS")
