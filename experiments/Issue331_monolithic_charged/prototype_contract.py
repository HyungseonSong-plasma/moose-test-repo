#!/usr/bin/env python3
"""Static contract for Issue #331 H_MONO_DD prototype.

This checker intentionally fails until `monolithic_charged.i` exists and satisfies
all architecture invariants.  It prevents a nominally-monolithic prototype from
silently retaining the old Poisson MultiApp/Gummel path or frozen charge fields.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "monolithic_charged.i"

CHARGED_VARS = ("log_e", "n_epsilon", "w_O2p", "w_Om", "w_Op", "potential_plasma")
FORBIDDEN = (
    "FullSolveMultiApp",
    "fixed_point_max_its",
    "fixed_point_rel_tol",
    "fixed_point_abs_tol",
    "log_e_frozen",
    "w_O2p_frozen",
    "w_Om_frozen",
    "w_Op_frozen",
    "potential_from_poisson",
)


def check(text: str) -> None:
    for variable in CHARGED_VARS:
        assert f"[{variable}]" in text, f"missing nonlinear charged variable {variable}"

    for token in FORBIDDEN:
        assert token not in text, f"segregated/Gummel token remains: {token}"

    # Electron + energy must couple directly to the nonlinear potential.
    assert "type = PhysicsFVLogMolarElectrostaticDrift" in text
    assert "type = PhysicsFVElectrostaticDrift" in text
    assert "type = PhysicsFVElectronEnergyJouleHeating" in text
    assert text.count("potential = potential_plasma") >= 3

    # Ordinary Poisson remains the physical equation.
    assert "variable = potential_plasma" in text
    assert "type = FVDiffusion" in text
    assert "type = FVCoupledForce" in text
    assert "v = poisson_charge_source" in text

    # Charged-heavy physics must not collapse to pure drift-diffusion.
    for species in ("O2p", "Om", "Op"):
        assert f"[{species}_time]" in text
        assert f"[{species}_advection]" in text
        assert f"[{species}_diffusion]" in text
        assert f"[{species}_drift]" in text
    assert "mass_frame" in text.lower(), "missing charged-heavy mass-frame correction"

    # One Newton system, no outer fixed point.
    assert "solve_type = NEWTON" in text
    assert "automatic_scaling = true" in text
    assert "off_diagonals_in_auto_scaling = true" in text


def main() -> None:
    if not INPUT.exists():
        raise SystemExit("UNRESOLVED: monolithic_charged.i has not been implemented yet")
    check(INPUT.read_text(encoding="utf-8"))
    print("ISSUE331_MONOLITHIC_STATIC_CONTRACT: PASS")


if __name__ == "__main__":
    main()
