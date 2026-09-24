#!/usr/bin/env python3
"""Issue #331 Stage-C static Jacobian contract.

This is deliberately a structural proof, not a performance claim.  It checks
that the eventual Stage-B input exposes both directions of the charged/Poisson
Newton coupling and fails closed if any charge state is lagged/frozen.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "monolithic_charged.i"

CHARGED = ("log_e", "w_O2p", "w_Om", "w_Op")
LAGGED = (
    "log_e_frozen", "w_O2p_frozen", "w_Om_frozen", "w_Op_frozen",
    "potential_from_poisson", "potential_fast",
)


def check(text: str) -> None:
    # Charged residual -> potential: accepted AD drift/Joule owners must consume
    # the nonlinear potential directly in the same problem.
    assert "type = PhysicsFVLogMolarElectrostaticDrift" in text
    assert text.count("type = PhysicsFVElectrostaticDrift") >= 3
    assert "type = PhysicsFVElectronEnergyJouleHeating" in text
    assert text.count("potential = potential_plasma") >= 5

    # Potential residual -> charged state: ordinary Poisson must consume an AD
    # charge functor constructed directly from nonlinear charged variables.
    assert "type = QPXPlasmaChargeDensityMaterial" in text
    assert "electron_density = n_e_physical" in text
    assert "ion_mass_fractions = 'w_O2p w_Om w_Op'" in text
    assert "ion_charges = '1 -1 1'" in text
    assert "type = FVCoupledForce" in text
    assert "v = poisson_charge_source" in text

    # n_e_physical must be an AD functor of log_e, not an AuxVariable/cache.
    assert "property_name = n_e_physical" in text
    assert "functor_names = 'log_e'" in text
    assert "exp(loge)" in text
    for token in LAGGED:
        assert token not in text, f"lagged coupling remains: {token}"

    # All charge owners are nonlinear variables in this problem.
    for var in CHARGED + ("potential_plasma",):
        assert f"[{var}]" in text, f"missing nonlinear owner: {var}"


def main() -> None:
    if not INPUT.exists():
        raise SystemExit("UNRESOLVED: monolithic_charged.i not implemented; Jacobian proof cannot pass")
    check(INPUT.read_text(encoding="utf-8"))
    print("ISSUE331_MONOLITHIC_JACOBIAN_CONTRACT: PASS")


if __name__ == "__main__":
    main()
