#!/usr/bin/env python3
"""Physics #17 R1 EI01 attachment particle-source discriminator.

This is deliberately framework-independent: it proves the frozen algebra/sign/unit contract
before the controlled MOOSE runtime discriminator in the next controller step.
"""

import math

N_A = 6.02214076e23
M_O = 15.999e-3
M_O2 = 2.0 * M_O


def sources_from_one_progress(R_attachment_molar, n_ref):
    """Sources generated from one canonical R_attachment [mol/(m^3 s)]."""
    if R_attachment_molar < 0.0:
        raise ValueError("R_attachment must be non-negative")
    if n_ref <= 0.0:
        raise ValueError("n_ref must be positive")

    return {
        "electron_number": -N_A * R_attachment_molar,
        "O2_mass": -M_O2 * R_attachment_molar,
        "O_mass": M_O * R_attachment_molar,
        "Om_mass": M_O * R_attachment_molar,
        "electron_normalized": -N_A * R_attachment_molar / n_ref,
    }


def charge_number_ledger(e_source, om_molar_source):
    # Charges z_e = -1 and z_Om = -1.  O2 and O are neutral.
    return -e_source - N_A * om_molar_source


def main():
    R = 2.5  # mol/(m^3 s), arbitrary discriminator magnitude
    n_ref = 4.0e16
    s = sources_from_one_progress(R, n_ref)

    # Sign discriminator for e + O2 -> O + Om.
    assert s["electron_number"] < 0.0
    assert s["O2_mass"] < 0.0
    assert s["O_mass"] > 0.0
    assert s["Om_mass"] > 0.0

    # Heavy mass and oxygen-atom conservation from the SAME R_attachment.
    assert math.isclose(s["O2_mass"] + s["O_mass"] + s["Om_mass"], 0.0, abs_tol=1e-14)
    oxygen_atom_molar = -2.0 * R + R + R
    assert math.isclose(oxygen_atom_molar, 0.0, abs_tol=1e-14)

    # Charge including electrons: electron loss balances Om production.
    assert math.isclose(charge_number_ledger(s["electron_number"], R), 0.0, abs_tol=1e-6)

    # Normalization: n_e_phys = n_ref*n_e_hat => S_hat = S_phys/n_ref.
    assert math.isclose(s["electron_normalized"] * n_ref, s["electron_number"], rel_tol=1e-15)

    # Frozen table-unit interpretation: k_raw [m^3/(mol s)] and
    # k_particle = k_raw/N_A [m^3/s] are algebraically identical.
    k_raw = 3.7e9
    n_e = 1.2e16
    c_o2 = 0.031  # mol/m^3
    R_molar = k_raw * (n_e / N_A) * c_o2
    R_particle_basis = (k_raw / N_A) * n_e * c_o2
    assert math.isclose(R_molar, R_particle_basis, rel_tol=1e-15)

    # Mutation controls: wrong electron sign and duplicate/perturbed rate must fail
    # the charge ledger rather than silently appearing acceptable.
    wrong_sign_e = +N_A * R
    assert not math.isclose(charge_number_ledger(wrong_sign_e, R), 0.0, abs_tol=1e-6)

    independently_recomputed_om_rate = 1.01 * R
    assert not math.isclose(
        charge_number_ledger(s["electron_number"], independently_recomputed_om_rate),
        0.0,
        abs_tol=1e-6,
    )

    print("EI01_ATTACHMENT_SOURCE_CONTRACT_PASS")


if __name__ == "__main__":
    main()
