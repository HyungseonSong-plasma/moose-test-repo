"""Guard retired, unconsumed PhysicsApp implementation classes.

This contract is scoped to source ownership. It is not a substitute for
native MOOSE compilation or scientific regression acceptance.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"

RETIRED_FILES = (
    "src/functormaterials/PhysicsIonWallTotalFluxMaterial.C",
    "src/materials/PhysicsElectronDiffusionSurfaceCharge.C",
    "include/materials/PhysicsElectronDiffusionSurfaceCharge.h",
    "src/materials/PhysicsIonDriftSurfaceCharge.C",
    "include/materials/PhysicsIonDriftSurfaceCharge.h",
    "src/materials/PhysicsElectronSurfaceChargeMaterial.C",
    "include/materials/PhysicsElectronSurfaceChargeMaterial.h",
    "src/materials/PhysicsInverseCrossSection.C",
    "include/materials/PhysicsInverseCrossSection.h",
    "src/materials/PhysicsTotalCrossSection.C",
    "include/materials/PhysicsTotalCrossSection.h",
    "src/utils/PhysicsUtils.C",
    "include/utils/PhysicsUtils.h",
)
RETIRED_BCS = (
    "PhysicsFEMElectronGroundedSheathBC",
    "PhysicsFEMElectronGroundedSheathEnergyBC",
    "PhysicsFEMIonWallBC",
)
# The original electron log-molar grounded-sheath classes are retired.
# Electrons now use one particle/one energy BC and share the canonical flux;
# the heavy-ion log-molar wall BC remains an independent Native owner.
RETIRED_ELECTRON_BCS = (
    "PhysicsFEMLogMolarElectronGroundedSheathBC",
    "PhysicsFEMLogMolarElectronGroundedSheathEnergyBC",
)
ACTIVE_ELECTRON_BCS = ("FEMElectronSheathBC", "FEMElectronEnergySheathBC")
ACTIVE_ION_BCS = ("PhysicsFEMLogMolarIonWallBC",)


def test_unused_legacy_files_stay_absent():
    for rel in RETIRED_FILES:
        assert not (APP / rel).exists(), f"Retired object was reintroduced: {rel}"


def test_active_log_molar_wall_boundary_conditions_remain():
    # Never resurrect archived electron BC classes in either the old mixed
    # header/source or the new electron-specific files.
    source = (APP / "src/bcs/PhysicsFEMPlasmaWallBCs.C").read_text(encoding="utf-8")
    header = (APP / "include/bcs/PhysicsFEMPlasmaWallBCs.h").read_text(encoding="utf-8")
    for name in (*RETIRED_BCS, *RETIRED_ELECTRON_BCS):
        assert name not in source
        assert name not in header
    for name in ACTIVE_ION_BCS:
        assert f'class {name} : public ADIntegratedBC' in header
        assert f'registerMooseObject("PhysicsApp", {name});' in source
        assert f'{name}::computeQpResidual()' in source
    for name in ACTIVE_ELECTRON_BCS:
        native = (APP / "src/bcs" / f"{name}.C").read_text(encoding="utf-8")
        assert f'class {name} : public ADIntegratedBC' in native
        assert f'registerMooseObject("PhysicsApp", {name});' in native
        assert f'{name}::computeQpResidual()' in native
        assert name not in source and name not in header
        for retired in RETIRED_ELECTRON_BCS:
            assert retired not in native


def test_active_wall_and_surface_charge_owners_remain():
    for rel in (
        "src/functormaterials/PhysicsIonWallFluxMaterial.C",
        "src/kernels/PhysicsLowerDSurfaceCurrent.C",
        "src/bcs/PhysicsADSurfaceChargePoissonBC.C",
        "src/fvkernels/PhysicsFVLogMolarElectronTransport.C",
    ):
        assert (APP / rel).is_file(), f"Active physics owner missing: {rel}"
