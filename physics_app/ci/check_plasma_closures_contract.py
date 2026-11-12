#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

required = [
    ROOT / "include/materials/DDMaterial.h",
    ROOT / "src/materials/DDMaterial.C",
    ROOT / "include/materials/PhysicsElectronMeanEnergyMaterial.h",
    ROOT / "src/materials/PhysicsElectronMeanEnergyMaterial.C",
    ROOT / "include/materials/PhysicsElectronImpactRateMaterial.h",
    ROOT / "src/materials/PhysicsElectronImpactRateMaterial.C",
    ROOT / "include/materials/NVMaterial.h",
    ROOT / "src/materials/NVMaterial.C",
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
electron = (ROOT / "src/materials/PhysicsElectronMeanEnergyMaterial.C").read_text()
single_ei = (ROOT / "src/materials/PhysicsElectronImpactRateMaterial.C").read_text()
heavy = (ROOT / "src/materials/NVMaterial.C").read_text()
drift = (ROOT / "src/materials/DDMaterial.C").read_text()

# The unused composition wrapper and its two dedicated Material classes are retired.
# Keep existing registered physics implementations, not generated C++ sources.
for old_type in ("PhysicsElectronKineticsMaterial", "PhysicsHeavyTransportMaterial"):
    assert not (ROOT / "src/materials" / (old_type + ".C")).exists()
    assert not (ROOT / "include/materials" / (old_type + ".h")).exists()

# The mean-energy state is a separate bridge; DDMaterial alone owns
# electron particle/energy transport coefficients and lookup interpolation.
assert '"mean_energy_output"' in electron
for name in ('"electron_energy_mobility"', '"electron_energy_diffusion"',
             '"electron_mobility"', '"electron_diffusion"'):
    assert name in drift

# Current EI progresses use an existing one-reaction-per-material owner.
assert "rate_table_file" in single_ei
assert "reaction_progress" in single_ei
assert 'registerMooseObject("PhysicsApp", PhysicsElectronImpactRateMaterial);' in single_ei
# Existing heavy diffusion implementation outlives its retired naming wrapper.
assert 'registerMooseObject("PhysicsApp", NVMaterial);' in heavy
assert 'registerMooseObject("PhysicsApp", DDMaterial);' in drift

# Native input explicitly uses existing classes; no source-code generation.
fixture = (ROOT / "ci/plasma_direct_existing_materials_smoke.i").read_text()
for old_type in ("PhysicsElectronKineticsMaterial", "PhysicsHeavyTransportMaterial"):
    assert "type = " + old_type not in fixture
for type_name in ("DDMaterial", "PhysicsElectronImpactRateMaterial",
                  "NVMaterial", "PhysicsPlasmaChargeDensityMaterial"):
    assert "type = " + type_name in fixture
assert fixture.count("type = PhysicsElectronImpactRateMaterial") == 2

# Keep the separate NV alias while retiring electron-lookup factory spellings.
for legacy in (
    "PhysicsElectronMeanEnergyMaterial.C",
    "DDMaterial.C",
    "PhysicsElectronImpactRateMaterial.C",
    "NVMaterial.C",
):
    assert (ROOT / "src/materials" / legacy).is_file(), legacy


# Only the independent NV legacy name remains an active factory alias.
for old_type, new_type in (
    ("PhysicsThermalDiffusionMaterial", "NVMaterial"),
):
    source = ROOT / "src/materials" / (new_type + ".C")
    header = ROOT / "include/materials" / (new_type + ".h")
    assert source.is_file() and header.is_file(), (source, header)
    assert not (ROOT / "src/materials" / (old_type + ".C")).exists()
    assert not (ROOT / "include/materials" / (old_type + ".h")).exists()
    content = source.read_text()
    assert f'registerMooseObject("PhysicsApp", {new_type});' in content
    assert f'registerMooseObjectAliased("PhysicsApp", {new_type}, "{old_type}");' in content

# Electron lookup factory aliases and direct axis overrides are retired.
for old_type in ("ElectronTransportLookupMaterial", "PhysicsElectronTransportLookupMaterial"):
    assert f'registerMooseObjectAliased("PhysicsApp", DDMaterial, "{old_type}");' not in drift
for retired_option in ('"property_table_file"', '"coordinate"', '"mean_energy"'):
    assert retired_option not in drift
assert 'getFunctorByName<ADReal>("mean_en_solved")' in drift

# The old charged transport assembler is now redundant: DDMaterial owns
# per-species mu/D, standalone charge density retains Poisson/FV sources,
# and the FV/FEM transport kernels evaluate their actual face/volume fluxes.
for name in ("PlasmaChargeTransportMaterial", "PhysicsPlasmaChargeTransportMaterial"):
    assert not (ROOT / "src/materials" / (name + ".C")).exists()
    assert not (ROOT / "include/materials" / (name + ".h")).exists()
assert 'registerMooseObject("PhysicsApp", PhysicsPlasmaChargeDensityMaterial);' in (
    ROOT / "src/materials/PhysicsPlasmaChargeDensityMaterial.C").read_text()

print("RETIRED_PLASMA_CLOSURES_MATERIAL_CONTRACT: PASS")

# SpeciesTransportAliasMaterial has been absorbed into DDMaterial functor mode.
assert not (ROOT / "src/materials/SpeciesTransportAliasMaterial.C").exists()
assert not (ROOT / "include/materials/SpeciesTransportAliasMaterial.h").exists()

# The 6 retired transport-coefficient .h/.C implementations must not reappear.
for old_name in ("ElectronTransportLookupMaterial", "ElectronClosureMaterial", "PhysicsThermalDiffusionMaterial",
                 "PhysicsElectronTransportCoefficients"):
    assert not (ROOT / "src/materials" / (old_name + ".C")).exists()
    assert not (ROOT / "include/materials" / (old_name + ".h")).exists()
