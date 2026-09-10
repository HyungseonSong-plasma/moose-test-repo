#!/usr/bin/env python3
"""Contract discriminator for #26 E8 bounded EI10 inelastic electron-energy coupling."""

import json
import math
from pathlib import Path

N_A = 6.02214076e23
CONTRACT = Path("docs/development/2026-09-10_issue26_e8_ei10_energy_contract.json")
RATE_OWNER = Path("physics_app/src/materials/PhysicsElectronImpactO2sExcitationMaterial.C")


def main():
    c = json.loads(CONTRACT.read_text())
    r = c["reaction"]
    own = c["ownership"]
    norm = c["normalization"]
    guard = c["identity_guards"]

    assert c["work_issue"] == 26
    assert c["controller_issue"] == 176
    assert c["controller_stage"] == "STAGE_4_E8"
    assert c["bounded_step"] == "E8_I1_EI10_INELASTIC_ENERGY_OWNERSHIP_CONTRACT"
    assert c["prior_acceptance"]["E0_E7"] == "PASS_FROZEN"
    assert c["prior_acceptance"]["stage3_R1_R2_R3_particle_heavy"] == "PASS_BOUNDED_CONTROLLED"

    assert r["id"] == "EI10_O2_TO_O2S"
    assert r["canonical_progress"] == "R_O2s"
    assert r["canonical_progress_units"] == "mol/(m^3 s)"
    assert r["energy_loss_eV_per_event"] == 0.977
    assert r["net_electron_particle_stoich"] == 0

    assert own["canonical_rate_owner"] == "PhysicsElectronImpactO2sExcitationMaterial"
    assert own["particle_source_projector"] == "PhysicsO2sExcitationSourceMaterial"
    assert own["energy_projection_owner"] == "PhysicsFVElectronReactionEnergySource"
    assert own["energy_projection_must_consume"] == "R_O2s"
    assert own["energy_projection_must_not_recompute_rate"] is True
    assert own["normalized_equation_variable"] == "n_epsilon_hat"

    assert norm["physical_energy_source_eV_m3_s"] == "S_epsilon = -Delta_epsilon_eV * N_A * R_O2s"
    assert norm["normalized_rhs"] == "S_hat = S_epsilon / (n_ref * epsilon_ref_eV)"
    assert norm["fv_residual_convention"] == "residual contribution = -S_hat"
    assert norm["required_parameters"] == [
        "reaction_progress", "energy_loss_eV", "n_ref", "energy_reference_eV"
    ]

    assert guard["required_channel"] == "O2(a1Delta_g)"
    assert guard["required_energy_loss_eV"] == 0.977
    assert guard["forbidden_substitute"] == "user_supplied:o2_excitation_9p97"
    assert "not EI10" in guard["forbidden_reason"]

    # Existing Stage-3 rate owner must remain the single EI10 kinetic evaluator.
    rate = RATE_OWNER.read_text()
    assert 'addFunctorProperty<ADReal>(\n      "R_O2s"' in rate
    assert "K_O2S = 4.71e8" in rate
    assert "electron-energy coupling remains deferred to #26 E8" in rate
    assert "0.977" not in rate
    assert "9.97" not in rate

    # Independent sign/unit/normalization discriminator.
    R = 1.25e-3  # mol/(m^3 s), arbitrary positive progress
    n_ref = 1.0e16
    epsilon_ref = 5.73276
    delta_e = r["energy_loss_eV_per_event"]
    physical = -delta_e * N_A * R
    normalized_rhs = physical / (n_ref * epsilon_ref)
    residual = -normalized_rhs

    assert physical < 0.0
    assert normalized_rhs < 0.0
    assert residual > 0.0
    assert math.isclose(
        residual,
        delta_e * N_A * R / (n_ref * epsilon_ref),
        rel_tol=1.0e-15,
    )

    # Mutation controls.
    assert (+delta_e * N_A * R) > 0.0
    assert not math.isclose(9.97, delta_e, rel_tol=0.0, abs_tol=1.0e-12)

    assert c["runtime_acceptance"]["required"] is True
    assert "bounded EI10 E8" in c["runtime_acceptance"]["minimum_claim"]
    assert "full real-QVT" in c["runtime_acceptance"]["must_not_claim"]

    print("E8_EI10_INELASTIC_ENERGY_CONTRACT_PASS")


if __name__ == "__main__":
    main()
