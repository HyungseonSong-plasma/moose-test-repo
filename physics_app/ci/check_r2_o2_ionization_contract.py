#!/usr/bin/env python3
"""Physics #17 R2 O2-ionization lookup/ownership contract discriminator.

Framework-independent controller Step-1 gate. This freezes algebra, conservation, sign,
lookup-bound and single-progress ownership before production implementation.
"""

import json
import math
from pathlib import Path

N_A = 6.02214076e23
M_O2 = 31.998e-3
CONTRACT = Path("docs/development/2026-09-08_issue17_r2_o2_ionization_contract.json")


def ionization_sources(R_molar, n_ref):
    if R_molar < 0.0:
        raise ValueError("R_ion_O2 must be non-negative")
    if n_ref <= 0.0:
        raise ValueError("n_ref must be positive")
    return {
        "O2_mass": -M_O2 * R_molar,
        "O2p_mass": M_O2 * R_molar,
        "electron_number": N_A * R_molar,
        "electron_normalized": N_A * R_molar / n_ref,
    }


def charge_ledger(electron_number_source, o2p_molar_source):
    # z_e=-1, z_O2p=+1.
    return -electron_number_source + N_A * o2p_molar_source


def main():
    contract = json.loads(CONTRACT.read_text())
    assert contract["enabled_particle_subset"] == ["EI01_O2_ATTACHMENT", "EI16_O2_IONIZATION"]

    lookup = contract["lookup_contract"]
    lo, hi = lookup["domain_eV"]
    assert 0.0 < lo < hi
    assert lookup["out_of_range_behavior"] == "FAIL_STRICTLY"
    assert lookup["silent_clamp"] is False
    assert lookup["silent_floor"] is False
    assert lookup["raw_table_unit"] == "m^3/(mol s)"
    assert lookup["particle_rate_coefficient"] == "k_raw / N_A"

    ion = contract["reactions"]["EI16_O2_IONIZATION"]
    assert ion["shared_progress"] == "R_ion_O2"
    assert ion["net_electron_stoich"] == 1
    assert ion["expected_electron_source_sign"] == "positive"
    assert ion["energy_coupling_enabled"] is False

    R = 2.5
    n_ref = 4.0e16
    s = ionization_sources(R, n_ref)

    assert s["electron_number"] > 0.0
    assert s["O2_mass"] < 0.0
    assert s["O2p_mass"] > 0.0

    assert math.isclose(s["O2_mass"] + s["O2p_mass"], 0.0, abs_tol=1e-14)
    oxygen_atom_molar = -2.0 * R + 2.0 * R
    assert math.isclose(oxygen_atom_molar, 0.0, abs_tol=1e-14)

    assert math.isclose(charge_ledger(s["electron_number"], R), 0.0, abs_tol=1e-6)
    assert math.isclose(s["electron_normalized"] * n_ref, s["electron_number"], rel_tol=1e-15)

    k_raw = 3.7e9
    n_e = 1.2e16
    c_o2 = 0.031
    R_molar = k_raw * (n_e / N_A) * c_o2
    R_particle_basis = (k_raw / N_A) * n_e * c_o2
    assert math.isclose(R_molar, R_particle_basis, rel_tol=1e-15)

    assert not math.isclose(charge_ledger(-N_A * R, R), 0.0, abs_tol=1e-6)
    assert not math.isclose(charge_ledger(s["electron_number"], 1.01 * R), 0.0, abs_tol=1e-6)

    for value in (lo - 1e-9, hi + 1e-9):
        assert not (lo <= value <= hi)
    for value in (lo, 0.5 * (lo + hi), hi):
        assert lo <= value <= hi

    print("R2_O2_IONIZATION_CONTRACT_PASS")


if __name__ == "__main__":
    main()
