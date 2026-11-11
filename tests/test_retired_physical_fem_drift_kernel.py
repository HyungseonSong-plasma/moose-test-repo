"""Retire only the physical-state FEM drift-diffusion Kernel.

The log-molar solver operator and both electron Joule-work variants remain
available while S6 D P3/energy-source ownership is verified independently.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "physics_app/include/kernels/PhysicsFEMPlasmaTransport.h"
SOURCE = ROOT / "physics_app/src/kernels/PhysicsFEMPlasmaTransport.C"


def test_physical_state_drift_kernel_is_not_registered_or_defined():
    for path in (HEADER, SOURCE):
        text = path.read_text(encoding="utf-8")
        assert "PhysicsFEMPlasmaDriftDiffusion" not in text, path


def test_log_molar_drift_and_both_joule_kernels_are_unchanged_owners():
    header = HEADER.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")
    for name in (
        "PhysicsFEMLogMolarDriftDiffusion",
        "PhysicsFEMElectronJouleHeating",
        "PhysicsFEMLogMolarElectronJouleHeating",
    ):
        assert f"class {name} :" in header
        assert f'registerMooseObject("PhysicsApp", {name});' in source
        assert f"{name}::computeQpResidual()" in source
    assert "PhysicsFEMLogMolarTimeDerivative" in source
