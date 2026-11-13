"""Source-bound P0: active electron wall names and retired legacy producers."""
from pathlib import Path
import importlib.util

import pytest

ROOT = Path(__file__).resolve().parents[1]
BCS = ROOT / "physics_app/src/bcs"
OLD_CLASSES = (
    "PhysicsFEMLogMolarElectronGroundedSheathBC",
    "PhysicsFEMLogMolarElectronGroundedSheathEnergyBC",
    "PhysicsFEMLogMolarElectronFieldLimitedFluxBC",
    "PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC",
)


def test_active_classes_are_exactly_registered_and_source_split():
    owners = {
        "FEMElectronSheathBC": BCS / "FEMElectronSheathBC.C",
        "FEMElectronEnergySheathBC": BCS / "FEMElectronEnergySheathBC.C",
    }
    assert not (BCS / "PhysicsFEMLogMolarElectronFieldLimitedFluxBC.C").exists()
    for name, file in owners.items():
        text = file.read_text()
        assert f'class {name} : public ADIntegratedBC' in text
        assert text.count(f'registerMooseObject("PhysicsApp", {name});') == 1
        assert f"{name}::computeQpResidual()" in text
        assert 'getFunctor<ADReal>("wall_number_flux")' in text
        assert "Moose::FaceArg face_arg" in text
        assert "hasFaceSide(*fi, true)" in text
        assert "hasFaceSide(*fi, false)" in text
    assert "(2.5 * Te)" in owners["FEMElectronEnergySheathBC"].read_text()
    assert "/ PHYSICS_CONSTANTS::N_A" in owners["FEMElectronSheathBC"].read_text()


def test_retired_grounded_sheath_has_no_live_cpp_registration():
    h = (ROOT / "physics_app/include/bcs/PhysicsFEMPlasmaWallBCs.h").read_text()
    c = (BCS / "PhysicsFEMPlasmaWallBCs.C").read_text()
    for old in OLD_CLASSES:
        assert old not in h + c
    assert 'registerMooseObject("PhysicsApp", PhysicsFEMLogMolarIonWallBC);' in c
    for path in BCS.glob("*.C"):
        active = path.read_text()
        assert all(f'registerMooseObject("PhysicsApp", {name});' not in active
                   for name in OLD_CLASSES)
    assert (BCS / "PhysicsFEMLogMolarElectronEnergyDielectricBC.C").is_file()


def test_retired_fem_generator_rejects_unreviewed_physics_substitution():
    source = ROOT / "experiments/fem_fvm_plasma_discriminator/prepare_cases.py"
    spec = importlib.util.spec_from_file_location("discriminator_prepare", source)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pytest.raises(RuntimeError, match="RETIRED_GROUNDED_SHEATH_BCS"):
        mod.fem()
    file = ROOT / "experiments/fem_fvm_plasma_discriminator/prepare_full_fem_contour_mesh.py"
    assert "RETIRED_GROUNDED_SHEATH_BCS" in file.read_text()


def test_current_s6_preparer_only_emits_canonical_sheath_classes():
    generator = (ROOT / "experiments/Issue395_powered_chemistry_ladder/"
                 "enable_electron_adjacent_sheath_wall.py").read_text()
    assert "type = FEMElectronSheathBC" in generator
    assert "type = FEMElectronEnergySheathBC" in generator
    assert "PhysicsFEMLogMolarElectronEnergyDielectricBC" in generator  # input migration, not deletion
    for old in OLD_CLASSES:
        assert old not in generator
