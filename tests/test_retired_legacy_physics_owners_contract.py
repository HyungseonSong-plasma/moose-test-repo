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
    "src/fvkernels/PhysicsFVLogMolarElectronTransport.C",
    "include/fvkernels/PhysicsFVLogMolarElectronTransport.h",
    "src/utils/PhysicsUtils.C",
    "include/utils/PhysicsUtils.h",
)
RETIRED_BCS = (
    "PhysicsFEMElectronGroundedSheathBC",
    "PhysicsFEMElectronGroundedSheathEnergyBC",
    "PhysicsFEMIonWallBC",
)
ACTIVE_BCS = (
    "PhysicsFEMLogMolarElectronGroundedSheathBC",
    "PhysicsFEMLogMolarElectronGroundedSheathEnergyBC",
    "PhysicsFEMLogMolarIonWallBC",
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


def test_active_wall_and_surface_charge_owners_remain():
    for rel in (
        "src/functormaterials/PhysicsIonWallFluxMaterial.C",
        "src/kernels/PhysicsLowerDSurfaceCurrent.C",
        "src/bcs/PhysicsADSurfaceChargePoissonBC.C",
        "src/fvkernels/PhysicsFVLogMolarTransport.C",
    ):
        assert (APP / rel).is_file(), f"Active physics owner missing: {rel}"


def test_shared_fv_log_molar_transport_keeps_ion_operators_without_dead_source():
    source = (APP / "src/fvkernels/PhysicsFVLogMolarTransport.C").read_text(encoding="utf-8")
    header = (APP / "include/fvkernels/PhysicsFVLogMolarTransport.h").read_text(encoding="utf-8")
    for name in (
        "PhysicsFVLogMolarTimeDerivative",
        "PhysicsFVLogMolarDiffusion",
        "PhysicsFVLogMolarElectrostaticDrift",
    ):
        assert f"class {name} :" in header
        assert f'registerMooseObject("PhysicsApp", {name});' in source
    for removed in (
        "PhysicsFVLogMolarElectronReactionSource",
        "PhysicsFVLogMolarElectronTimeDerivative",
        "PhysicsFVLogMolarElectronDiffusion",
    ):
        assert removed not in header and removed not in source
    assert "return (exp(log_c_new) - exp(log_c_old)) / _dt;" in source
    assert "return -coeff_face * (c_neighbor - c_elem) / _face_info->dCNMag();" in source
    assert "_charge_number * mobility_face * (electric_field * _normal)" in source
    assert "const ADReal c_face = exp(_var(transported_face, state));" in source
    assert "use_element_gradient_for_potential" in source


def test_current_fv_ion_callers_use_only_generic_transport_classes():
    callers = (
        "experiments/fem_fvm_plasma_discriminator/prepare_cases.py",
        "experiments/fem_fvm_plasma_discriminator/prepare_ion_fvm_hybrid_contour.py",
    )
    for rel in callers:
        data = (ROOT / rel).read_text(encoding="utf-8")
        assert "PhysicsFVLogMolarTimeDerivative" in data
        assert "PhysicsFVLogMolarDiffusion" in data
        assert "PhysicsFVLogMolarElectronTimeDerivative" not in data
        assert "PhysicsFVLogMolarElectronDiffusion" not in data


def test_pinned_s6_base_retains_its_historical_fv_factory_names():
    source = (ROOT / "experiments/Issue402_plasma_dsl_g1/native/"
              "s6_c0_physics_base_no_d1.i").read_text(encoding="utf-8")
    assert source.count("type = PhysicsFVLogMolarElectronTimeDerivative") == 3
    assert source.count("type = PhysicsFVLogMolarElectronDiffusion") == 3
    assert "type = PhysicsFVLogMolarTimeDerivative" not in source
    assert "type = PhysicsFVLogMolarDiffusion" not in source
    preparer = (ROOT / "experiments/Issue402_plasma_dsl_g1/"
                "public_option_s6_p2.py").read_text(encoding="utf-8")
    assert "STAGED_D_FV_LOG_MOLAR_OWNER_COUNT_CHANGED" in preparer

