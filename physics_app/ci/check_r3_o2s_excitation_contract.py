#!/usr/bin/env python3
"""Physics #176 R3 O2(a1Delta_g) excitation ownership/constant-surrogate discriminator.

Framework-independent Stage-3 Step-1 gate. This freezes the user-authorized constant
surrogate, source ownership and conservation identities before production implementation.
It intentionally does not implement or validate the deferred electron-energy sink.
"""

import json
import math
from pathlib import Path

N_A = 6.02214076e23
M_O2 = 31.998e-3
CONTRACT = Path("docs/development/2026-09-10_issue17_r3_o2s_excitation_contract.json")


def o2s_sources(R_molar):
    if R_molar < 0.0:
        raise ValueError("R_O2s must be non-negative")
    return {
        "O2_mass": -M_O2 * R_molar,
        "O2s_mass": M_O2 * R_molar,
        "electron_number": 0.0,
    }


def heavy_mass_ledger(o2_mass, o2s_mass):
    return o2_mass + o2s_mass


def oxygen_atom_ledger(o2_molar_source, o2s_molar_source):
    return 2.0 * o2_molar_source + 2.0 * o2s_molar_source


def charge_ledger(electron_number_source):
    # O2 and O2(a1Delta_g) are neutral; EI10 has one electron on both sides.
    return -electron_number_source


def main():
    contract = json.loads(CONTRACT.read_text())

    assert contract["schema_version"] == 1
    assert contract["execution_issue"] == 176
    assert contract["controller_batch"] == "R3_O2S_EXCITATION"
    assert contract["controlled_stage3_subset"] == [
        "EI01_O2_ATTACHMENT",
        "EI16_O2_IONIZATION",
        "EI10_O2_TO_O2S",
    ]
    assert contract["prior_acceptance"]["EI01_O2_ATTACHMENT"]["net_electron_stoich"] == -1
    assert contract["prior_acceptance"]["EI16_O2_IONIZATION"]["net_electron_stoich"] == 1
    assert contract["prior_acceptance"]["EI16_O2_IONIZATION"]["integrated_physics_accuracy"] == "NOT_ESTABLISHED"

    reaction = contract["reaction"]
    assert reaction["id"] == "EI10_O2_TO_O2S"
    assert reaction["formula"] == "e + O2(X3Sigma_g-) -> e + O2(a1Delta_g)"
    assert reaction["state"] == "R3_READY_CONTRACT_FROZEN"
    assert reaction["reactants"] == {"e": 1, "O2": 1}
    assert reaction["products"] == {"e": 1, "O2s": 1}
    assert reaction["net_electron_stoich"] == 0
    assert reaction["expected_electron_particle_source"] == 0.0
    assert reaction["shared_progress"] == "R_O2s"
    assert reaction["molar_progress"] == "R_O2s = k_physics_const * (n_e_physical / N_A) * c_O2"
    assert "one canonical R_O2s" in reaction["shared_progress_rule"]
    assert "independent electron-particle or electron-energy rate evaluation" in reaction["shared_progress_rule"]

    states = reaction["state_inputs"]
    assert states["electron_number_density"] == "n_e_physical = n_ref * n_e_hat"
    assert states["constrained_o2_mass_fraction"].startswith("w_O2 = 1 - (w_O2s + w_O2p")
    assert states["o2_molar_concentration"] == "c_O2 = rho * w_O2 / M_O2"

    model = contract["constant_surrogate_model"]
    assert model["classification"] == "EXPLICIT_USER_AUTHORIZED_MODELING_DECISION"
    assert model["physical_channel_identity"] == "O2(a1Delta_g)"
    assert model["threshold_energy_eV"] == 0.977
    assert model["external_fit_temperature_range_eV"] == [1.0, 7.0]
    assert model["reference_mean_energy_eV"] == 5.73276
    assert model["maxwellian_relation"] == "mean_en = 1.5 * Te"
    assert model["forbidden_substitute"] == "user_supplied:o2_excitation_9p97"
    assert "not the 0.977 eV O2(a1Delta_g) channel" in model["forbidden_substitute_reason"]

    te_ref = (2.0 / 3.0) * model["reference_mean_energy_eV"]
    assert math.isclose(te_ref, model["reference_Te_eV"], rel_tol=0.0, abs_tol=1.0e-12)
    assert model["external_fit_temperature_range_eV"][0] <= te_ref <= model["external_fit_temperature_range_eV"][1]

    k_particle_derived = 1.37e-15 * math.exp(-2.14 / te_ref)
    assert math.isclose(
        k_particle_derived,
        model["derived_particle_coefficient_m3_per_s"],
        rel_tol=1.0e-6,
    )
    k_physics_derived = N_A * k_particle_derived
    assert math.isclose(
        k_physics_derived,
        model["derived_physics_molar_coefficient_m3_per_mol_s"],
        rel_tol=1.0e-6,
    )
    assert math.isclose(
        model["canonical_particle_coefficient_m3_per_s"],
        model["derived_particle_coefficient_m3_per_s"],
        rel_tol=1.0e-3,
    )
    assert math.isclose(
        model["canonical_physics_molar_coefficient_m3_per_mol_s"],
        model["derived_physics_molar_coefficient_m3_per_mol_s"],
        rel_tol=1.0e-3,
    )
    assert model["molar_conversion"] == "k_physics = N_A * k_particle"

    ownership = contract["source_ownership"]
    assert ownership["heavy_sources"] == {
        "O2": "-M_O2 * R_O2s",
        "O2s": "+M_O2 * R_O2s",
    }
    assert ownership["electron_particle"] == "NO_SOURCE_FOR_EI10_NET_STOICHIOMETRY_ZERO"
    assert ownership["electron_energy"] == "DEFERRED_TO_STAGE_4_ISSUE_26_E8"
    assert ownership["energy_coupling_enabled"] is False

    R = 2.5
    sources = o2s_sources(R)
    assert sources["O2_mass"] < 0.0 < sources["O2s_mass"]
    assert sources["electron_number"] == 0.0
    assert math.isclose(
        heavy_mass_ledger(sources["O2_mass"], sources["O2s_mass"]),
        0.0,
        abs_tol=1.0e-14,
    )
    assert math.isclose(oxygen_atom_ledger(-R, R), 0.0, abs_tol=1.0e-14)
    assert math.isclose(charge_ledger(sources["electron_number"]), 0.0, abs_tol=0.0)

    # Mutation controls: each forbidden ownership/sign change must violate a frozen identity.
    assert not math.isclose(
        heavy_mass_ledger(sources["O2_mass"], 1.01 * sources["O2s_mass"]),
        0.0,
        abs_tol=1.0e-14,
    )
    assert not math.isclose(oxygen_atom_ledger(-R, 1.01 * R), 0.0, abs_tol=1.0e-14)
    assert not math.isclose(charge_ledger(N_A * 0.01 * R), 0.0, abs_tol=1.0e-6)
    assert model["canonical_physics_molar_coefficient_m3_per_mol_s"] != 9.97

    required = set(contract["pass_invariants"])
    assert {
        "single_R_O2s_ownership",
        "O2_O2s_equal_and_opposite_mass_sources",
        "heavy_mass",
        "oxygen_atoms",
        "charge_including_electron",
        "zero_electron_particle_source",
        "positive_finite_heavy_state",
        "constrained_O2_state_ownership",
        "constant_surrogate_identity_and_units",
        "9p97_eV_substitution_rejected",
        "no_stage3_electron_energy_source",
    } <= required

    runtime = contract["runtime_acceptance"]
    assert runtime["required"] is True
    assert runtime["execution_lane"] == "repository_governed_JIT_capable_Physics_science_lane"
    assert runtime["must_not_claim"] == "full real-QVT Integrated Physics Accuracy"

    print("R3_O2S_EXCITATION_CONTRACT_PASS")


if __name__ == "__main__":
    main()
