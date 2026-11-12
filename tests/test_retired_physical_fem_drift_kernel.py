"""Retire only the physical-state FEM drift-diffusion Kernel.

After approved B removal, both legacy physical-state drift and Joule
kernels are retired. Keep the log-molar transport and Joule owners intact.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "physics_app/include/kernels/FEMPlasmaTransport.h"
SOURCE = ROOT / "physics_app/src/kernels/FEMPlasmaTransport.C"


def test_physical_state_drift_kernel_is_not_registered_or_defined():
    for path in (HEADER, SOURCE):
        text = path.read_text(encoding="utf-8")
        assert "PhysicsFEMPlasmaDriftDiffusion" not in text, path


def test_log_molar_drift_and_joule_owners_remain():
    header = HEADER.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")
    for name in (
        "FEMLogMolarDriftDiffusion",
        "FEMLogMolarElectronJouleHeating",
    ):
        assert f"class {name} :" in header
        assert f'registerMooseObject("PhysicsApp", {name});' in source
        assert f"{name}::computeQpResidual()" in source
    assert "FEMLogMolarTimeDerivative" in source
    assert "PhysicsFEMElectronJouleHeating" not in header
    assert "PhysicsFEMElectronJouleHeating" not in source
