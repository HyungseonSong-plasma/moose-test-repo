"""Guard retired, unconsumed PhysicsApp implementation classes.

This contract is scoped to source ownership. It is not a substitute for
native MOOSE compilation or scientific regression acceptance.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"

RETIRED_FILES = (
    "src/functormaterials/PhysicsIonWallFluxMaterial.C",
    "include/functormaterials/PhysicsIonWallFluxMaterial.h",
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
    "PhysicsFEMLogMolarElectronGroundedSheathBC",
    "PhysicsFEMLogMolarElectronGroundedSheathEnergyBC",
    "PhysicsFEMLogMolarElectronFieldLimitedFluxBC",
    "PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC",
)
ACTIVE_BCS = ("PhysicsFEMLogMolarIonWallBC",)
ACTIVE_ELECTRON_BCS = (
    "FEMElectronSheathBC",
    "FEMElectronEnergySheathBC",
)


def test_unused_legacy_files_stay_absent():
    for rel in RETIRED_FILES:
        assert not (APP / rel).exists(), f"Retired object was reintroduced: {rel}"


def test_active_log_molar_wall_boundary_conditions_remain():
    source = (APP / "src/bcs/PhysicsFEMPlasmaWallBCs.C").read_text(encoding="utf-8")
    header = (APP / "include/bcs/PhysicsFEMPlasmaWallBCs.h").read_text(encoding="utf-8")
    for name in RETIRED_BCS:
        assert name not in source
        assert name not in header
    for name in ACTIVE_BCS:
        assert f'class {name} : public ADIntegratedBC' in header
        assert f'registerMooseObject("PhysicsApp", {name});' in source
        assert f'{name}::computeQpResidual()' in source

    # The retired composite grounded/field-limited electron classes are
    # replaced by two explicitly registered 4+4 flux-preserving BC owners.
    for name in ACTIVE_ELECTRON_BCS:
        path = APP / f"src/bcs/{name}.C"
        assert path.is_file(), f"Maintained electron sheath BC absent: {path}"
        text = path.read_text(encoding="utf-8")
        assert f"class {name} : public ADIntegratedBC" in text
        assert text.count(f'registerMooseObject("PhysicsApp", {name});') == 1
        assert f"{name}::computeQpResidual()" in text
        assert 'getFunctor<ADReal>("wall_number_flux")' in text
        assert "hasFaceSide(*fi, true)" in text
        assert "hasFaceSide(*fi, false)" in text
        for retired in RETIRED_BCS:
            assert f'registerMooseObject("PhysicsApp", {retired});' not in text
    assert "/ PHYSICS_CONSTANTS::N_A" in (
        APP / "src/bcs/FEMElectronSheathBC.C"
    ).read_text(encoding="utf-8")
    assert "(2.5 * Te)" in (
        APP / "src/bcs/FEMElectronEnergySheathBC.C"
    ).read_text(encoding="utf-8")


def test_active_wall_and_surface_charge_owners_remain():
    for rel in (
        "src/functormaterials/IonWallFluxMaterial.C",
        "include/functormaterials/IonWallFluxMaterial.h",
        "src/kernels/PhysicsLowerDSurfaceCurrent.C",
        "src/bcs/PhysicsADSurfaceChargePoissonBC.C",
        "src/fvkernels/PhysicsFVLogMolarElectronTransport.C",
    ):
        assert (APP / rel).is_file(), f"Active physics owner missing: {rel}"
