#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

required = [
    ROOT / "include/materials/DDTransportMaterial.h",
    ROOT / "src/materials/DDTransportMaterial.C",
    ROOT / "include/materials/PhysicsElectronMeanEnergyMaterial.h",
    ROOT / "src/materials/PhysicsElectronMeanEnergyMaterial.C",
    ROOT / "include/materials/EIRateCoefMaterial.h",
    ROOT / "src/materials/EIRateCoefMaterial.C",
    ROOT / "include/materials/NVTransportMaterial.h",
    ROOT / "src/materials/NVTransportMaterial.C",
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
single_ei = (ROOT / "src/materials/EIRateCoefMaterial.C").read_text()
heavy = (ROOT / "src/materials/NVTransportMaterial.C").read_text()
drift = (ROOT / "src/materials/DDTransportMaterial.C").read_text()

# The unused composition wrapper and its two dedicated Material classes are retired.
# Keep existing registered physics implementations, not generated C++ sources.
for old_type in ("PhysicsElectronKineticsMaterial", "PhysicsHeavyTransportMaterial"):
    assert not (ROOT / "src/materials" / (old_type + ".C")).exists()
    assert not (ROOT / "include/materials" / (old_type + ".h")).exists()

# The mean-energy state is a separate bridge; DDTransportMaterial alone owns
# electron particle/energy transport coefficients and lookup interpolation.
assert '"mean_energy_output"' in electron
for name in ('"electron_energy_mobility"', '"electron_energy_diffusion"',
             '"electron_mobility"', '"electron_diffusion"'):
    assert name in drift

# Current EI progresses use an existing one-reaction-per-material owner.
assert "rate_table_file" in single_ei
assert "reaction_progress" in single_ei
assert 'registerMooseObject("PhysicsApp", EIRateCoefMaterial);' in single_ei
# Existing heavy diffusion implementation outlives its retired naming wrapper.
assert 'registerMooseObject("PhysicsApp", NVTransportMaterial);' in heavy
assert 'registerMooseObject("PhysicsApp", DDTransportMaterial);' in drift

# Native input explicitly uses existing classes; no source-code generation.
fixture = (ROOT / "ci/plasma_direct_existing_materials_smoke.i").read_text()
for old_type in ("PhysicsElectronKineticsMaterial", "PhysicsHeavyTransportMaterial"):
    assert "type = " + old_type not in fixture
for type_name in ("DDTransportMaterial", "EIRateCoefMaterial",
                  "NVTransportMaterial", "PhysicsPlasmaChargeDensityMaterial"):
    assert "type = " + type_name in fixture
assert fixture.count("type = EIRateCoefMaterial") == 2

# Keep the separate NV alias while retiring electron-lookup factory spellings.
for legacy in (
    "PhysicsElectronMeanEnergyMaterial.C",
    "DDTransportMaterial.C",
    "EIRateCoefMaterial.C",
    "NVTransportMaterial.C",
):
    assert (ROOT / "src/materials" / legacy).is_file(), legacy


# No old registered Material names or C++ files: input writers must use canonical types.
for old_type in ("ElectronImpactRateMaterial", "PhysicsElectronImpactRateMaterial",
                 "DDMaterial", "NVMaterial", "PhysicsThermalDiffusionMaterial"):
    assert not (ROOT / "src/materials" / (old_type + ".C")).exists()
    assert not (ROOT / "include/materials" / (old_type + ".h")).exists()
for source in (single_ei, drift, heavy):
    assert 'registerMooseObjectAliased(' not in source

# Electron lookup factory aliases and direct axis overrides are retired.
for old_type in ("ElectronTransportLookupMaterial", "PhysicsElectronTransportLookupMaterial"):
    assert f'registerMooseObjectAliased("PhysicsApp", DDTransportMaterial, "{old_type}");' not in drift
for retired_option in ('"property_table_file"', '"coordinate"', '"mean_energy"'):
    assert retired_option not in drift
assert 'getFunctorByName<ADReal>("mean_en_solved")' in drift

# The old charged transport assembler is now redundant: DDTransportMaterial owns
# per-species mu/D, standalone charge density retains Poisson/FV sources,
# and the FV/FEM transport kernels evaluate their actual face/volume fluxes.
for name in ("PlasmaChargeTransportMaterial", "PhysicsPlasmaChargeTransportMaterial"):
    assert not (ROOT / "src/materials" / (name + ".C")).exists()
    assert not (ROOT / "include/materials" / (name + ".h")).exists()
assert 'registerMooseObject("PhysicsApp", PhysicsPlasmaChargeDensityMaterial);' in (
    ROOT / "src/materials/PhysicsPlasmaChargeDensityMaterial.C").read_text()

print("RETIRED_PLASMA_CLOSURES_MATERIAL_CONTRACT: PASS")

# SpeciesTransportAliasMaterial has been absorbed into DDTransportMaterial functor mode.
assert not (ROOT / "src/materials/SpeciesTransportAliasMaterial.C").exists()
assert not (ROOT / "include/materials/SpeciesTransportAliasMaterial.h").exists()

# The 6 retired transport-coefficient .h/.C implementations must not reappear.
for old_name in ("ElectronTransportLookupMaterial", "ElectronClosureMaterial", "PhysicsThermalDiffusionMaterial",
                 "PhysicsElectronTransportCoefficients"):
    assert not (ROOT / "src/materials" / (old_name + ".C")).exists()
    assert not (ROOT / "include/materials" / (old_name + ".h")).exists()
