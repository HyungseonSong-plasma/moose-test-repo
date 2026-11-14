"""Retire the Issue #224 no-gather-only Rhie-Chow ablation.

This cleanup does not affect the standard MOOSE INSFVRhieChowInterpolator or
the PhysicsApp dielectric surface-charge UserObjects.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_gather_diagnostic_retired():
    for directory, extension in (("src", "C"), ("include", "h")):
        legacy = (
            ROOT / "physics_app" / directory / "userobjects"
            / f"PhysicsDiagnosticNoGatherRhieChowInterpolator.{extension}"
        )
        assert not legacy.exists(), f"Diagnostic-only UserObject restored: {legacy}"

    assert not (
        ROOT / "experiments" / "Issue224_rc_gather_memory" / "run.py"
    ).exists(), "Retired no-gather ablation runner restored"


def test_surface_charge_userobjects_preserved():
    for cls in ("PhysicsSurfaceChargeState", "PhysicsSurfaceChargeStatePostprocessor"):
        for directory, extension in (("src", "C"), ("include", "h")):
            path = ROOT / "physics_app" / directory / "userobjects" / f"{cls}.{extension}"
            assert path.is_file(), f"Production-capable surface-charge object missing: {path}"
