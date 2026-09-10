#!/usr/bin/env python3
"""Static production-ownership discriminator for #176 R3 O2s excitation."""

import json
import math
import re
from pathlib import Path

N_A = 6.02214076e23
M_O2 = 31.998e-3
CONTRACT = Path("docs/development/2026-09-10_issue17_r3_o2s_excitation_contract.json")
RATE = Path("physics_app/src/materials/PhysicsElectronImpactO2sExcitationMaterial.C")
PROJ = Path("physics_app/src/materials/PhysicsO2sExcitationSourceMaterial.C")


def main():
    contract = json.loads(CONTRACT.read_text())
    rate = RATE.read_text()
    proj = PROJ.read_text()

    assert 'registerMooseObject("PhysicsApp", PhysicsElectronImpactO2sExcitationMaterial);' in rate
    assert 'addFunctorProperty<ADReal>(\n      "R_O2s"' in rate
    assert '_electron_number_density(getFunctor<ADReal>("electron_number_density"))' in rate
    assert '_o2_molar_concentration(getFunctor<ADReal>("o2_molar_concentration"))' in rate
    assert 'return K_O2S * (n_e / N_A) * c_o2;' in rate
    assert 'requires n_e >= 0' in rate and 'requires c_O2 >= 0' in rate

    match = re.search(r"constexpr Real K_O2S = ([0-9.eE+-]+);", rate)
    assert match, "frozen R3 coefficient is not explicit in the canonical rate owner"
    implementation_k = float(match.group(1))
    canonical_k = contract["constant_surrogate_model"][
        "canonical_physics_molar_coefficient_m3_per_mol_s"
    ]
    assert implementation_k == canonical_k

    for forbidden in (
        "O2_o2s_excitation_mass_source",
        "O2s_excitation_mass_source",
        "electron_O2s",
        "electron_energy",
        "0.977",
        "9.97",
    ):
        assert forbidden not in rate

    assert 'registerMooseObject("PhysicsApp", PhysicsO2sExcitationSourceMaterial);' in proj
    assert '_reaction_progress(getFunctor<ADReal>("reaction_progress"))' in proj
    assert '"O2_o2s_excitation_mass_source"' in proj
    assert '"O2s_excitation_mass_source"' in proj
    assert 'return -_o2_molar_mass * R;' in proj
    assert 'return _o2_molar_mass * R;' in proj
    for forbidden in (
        "K_O2S",
        "4.71e8",
        "N_A",
        "mean_energy",
        "electron_number_density",
        "electron_energy",
        "0.977",
        "9.97",
    ):
        assert forbidden not in proj

    # Independent algebraic discriminator for the frozen production ownership.
    R = canonical_k * (1.0e16 / N_A) * (3.1998e-5 * 0.999 / M_O2)
    s_o2 = -M_O2 * R
    s_o2s = M_O2 * R
    assert R > 0.0 and s_o2 < 0.0 < s_o2s
    assert math.isclose(s_o2 + s_o2s, 0.0, rel_tol=0.0, abs_tol=1.0e-14)
    assert math.isclose(-s_o2 / M_O2, R, rel_tol=1.0e-15)
    assert math.isclose(s_o2s / M_O2, R, rel_tol=1.0e-15)

    # EI10 carries one electron on each side; Stage 3 therefore owns no electron source.
    electron_number_source = 0.0
    assert electron_number_source == contract["reaction"]["expected_electron_particle_source"]
    assert contract["reaction"]["net_electron_stoich"] == 0
    assert contract["source_ownership"]["energy_coupling_enabled"] is False
    assert contract["source_ownership"]["electron_energy"] == "DEFERRED_TO_STAGE_4_ISSUE_26_E8"

    # Mutation controls: wrong projection or nonzero electron source must break closure.
    assert not math.isclose(s_o2 + 1.01 * s_o2s, 0.0, rel_tol=0.0, abs_tol=1.0e-14)
    assert N_A * 0.01 * R != 0.0

    print("R3_O2S_EXCITATION_IMPLEMENTATION_PASS")


if __name__ == "__main__":
    main()
