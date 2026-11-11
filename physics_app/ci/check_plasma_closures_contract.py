#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

required = [
    ROOT / "include/materials/ElectronClosureMaterial.h",
    ROOT / "src/materials/ElectronClosureMaterial.C",
    ROOT / "include/materials/PhysicsElectronKineticsMaterial.h",
    ROOT / "src/materials/PhysicsElectronKineticsMaterial.C",
    ROOT / "include/materials/PhysicsHeavyTransportMaterial.h",
    ROOT / "src/materials/PhysicsHeavyTransportMaterial.C",
    ROOT / "include/materials/PhysicsPlasmaChargeDensityMaterial.h",
    ROOT / "src/materials/PhysicsPlasmaChargeDensityMaterial.C",
]
for path in required:
    assert path.is_file(), path

app = (ROOT / "src/base/PhysicsApp.C").read_text()
assert 'PlasmaClosuresAction' not in app
assert 'PlasmaClosures/*' not in app
assert not (ROOT / "include/actions/PlasmaClosuresAction.h").exists()
assert not (ROOT / "src/actions/PlasmaClosuresAction.C").exists()
electron = (ROOT / "src/materials/ElectronClosureMaterial.C").read_text()
kinetics = (ROOT / "src/materials/PhysicsElectronKineticsMaterial.C").read_text()
heavy = (ROOT / "src/materials/PhysicsHeavyTransportMaterial.C").read_text()

# The retired Action was a composition wrapper, not a physics implementation.
# Preserve the independent Material registrations and legacy factory aliases.

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

# Backward compatibility: legacy *factory type names* remain registered;
# source filenames and C++ class identifiers now use the shorter canonical form.
for legacy in (
    "PhysicsElectronMeanEnergyMaterial.C",
    "ElectronTransportLookupMaterial.C",
    "PhysicsElectronImpactRateMaterial.C",
    "PhysicsThermalDiffusionMaterial.C",
):
    assert (ROOT / "src/materials" / legacy).is_file(), legacy


# MOOSE object-factory aliases keep immutable historical input decks valid.
for old_type, new_type in (
    ("PhysicsElectronClosureMaterial", "ElectronClosureMaterial"),
    ("PhysicsElectronTransportLookupMaterial", "ElectronTransportLookupMaterial"),
    ("PhysicsPlasmaChargeTransportMaterial", "PlasmaChargeTransportMaterial"),
    ("PhysicsSpeciesTransportAliasMaterial", "SpeciesTransportAliasMaterial"),
):
    source = ROOT / "src/materials" / (new_type + ".C")
    header = ROOT / "include/materials" / (new_type + ".h")
    assert source.is_file() and header.is_file(), (source, header)
    assert not (ROOT / "src/materials" / (old_type + ".C")).exists()
    assert not (ROOT / "include/materials" / (old_type + ".h")).exists()
    content = source.read_text()
    assert f'registerMooseObject("PhysicsApp", {new_type});' in content
    assert f'registerMooseObjectAliased("PhysicsApp", {new_type}, "{old_type}");' in content

print("RETIRED_PLASMA_CLOSURES_MATERIAL_CONTRACT: PASS")
