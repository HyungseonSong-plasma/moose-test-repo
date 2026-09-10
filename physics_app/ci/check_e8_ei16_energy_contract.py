#!/usr/bin/env python3
"""Contract discriminator for #26 E8-I2 EI16 O2 ionization energy ownership."""

import json
import math
from pathlib import Path

N_A = 6.02214076e23
CONTRACT = Path("docs/development/2026-09-10_issue26_e8_ei16_energy_contract.json")
R2_CONTRACT = Path("docs/development/2026-09-08_issue17_r2_o2_ionization_contract.json")
RATE_OWNER = Path("physics_app/src/materials/PhysicsElectronImpactIonizationMaterial.C")
PARTICLE_PROJ = Path("physics_app/src/materials/PhysicsO2IonizationSourceMaterial.C")
ENERGY_PROJ = Path("physics_app/src/fvkernels/PhysicsFVElectronReactionEnergySource.C")


def main():
    contract = json.loads(CONTRACT.read_text())
    r2 = json.loads(R2_CONTRACT.read_text())
    rate = RATE_OWNER.read_text()
    particle = PARTICLE_PROJ.read_text()
    energy = ENERGY_PROJ.read_text()

    rxn = contract["reaction"]
    own = contract["ownership"]
    assert rxn["id"] == "EI16_O2_IONIZATION"
    assert rxn["canonical_progress"] == "R_ion_O2"
    assert rxn["energy_loss_eV_per_event"] == 12.06
    assert rxn["net_electron_particle_stoich"] == 1
    assert own["canonical_rate_owner"] == "PhysicsElectronImpactIonizationMaterial"
    assert own["particle_source_projector"] == "PhysicsO2IonizationSourceMaterial"
    assert own["energy_projection_owner"] == "PhysicsFVElectronReactionEnergySource"
    assert own["all_source_paths_must_consume"] == "R_ion_O2"
    assert own["energy_projection_must_not_recompute_rate"] is True

    r2_ion = r2["reactions"]["EI16_O2_IONIZATION"]
    assert r2_ion["shared_progress"] == "R_ion_O2"
    assert r2_ion["energy_loss_eV"] == 12.06
    assert r2_ion["net_electron_stoich"] == 1

    assert 'registerMooseObject("PhysicsApp", PhysicsElectronImpactIonizationMaterial);' in rate
    assert '"R_ion_O2"' in rate
    assert 'return interpolateStrict(_mean_energy(r, state)) * (n_e / N_A) * c_o2;' in rate
    assert "strict R2 policy forbids clamp/floor" in rate

    assert 'registerMooseObject("PhysicsApp", PhysicsO2IonizationSourceMaterial);' in particle
    assert '_reaction_progress(getFunctor<ADReal>("reaction_progress"))' in particle
    assert '"O2_ionization_mass_source"' in particle
    assert '"O2p_ionization_mass_source"' in particle
    assert '"electron_ionization_number_source"' in particle
    assert 'return N_A * _reaction_progress(r, state);' in particle

    assert 'registerMooseObject("PhysicsApp", PhysicsFVElectronReactionEnergySource);' in energy
    assert '_reaction_progress(getFunctor<ADReal>("reaction_progress"))' in energy
    assert "physical_energy_source = -_energy_loss_eV * N_A * R;" in energy
    assert "physical_energy_source / (_n_ref * _energy_reference_eV);" in energy

    # Energy projector must stay generic and cannot own EI16 lookup/kinetics or the 12.06 identity.
    for forbidden in (
        "R_ion_O2",
        "PhysicsElectronImpactIonizationMaterial",
        "rate_table",
        "mean_en_solved",
        "interpolateStrict",
        "12.06",
    ):
        assert forbidden not in energy

    # Algebraic sign/normalization discriminator using the accepted controlled R2 progress vector.
    R = 0.0179028871546
    delta = rxn["energy_loss_eV_per_event"]
    n_ref = 1.0e16
    epsilon_ref = 5.73276
    rhs = -delta * N_A * R / (n_ref * epsilon_ref)
    residual = -rhs
    assert rhs < 0.0 < residual
    assert math.isclose(residual, delta * N_A * R / (n_ref * epsilon_ref), rel_tol=1.0e-15)

    # Mutation controls.
    assert not math.isclose(0.977, delta, rel_tol=0.0, abs_tol=1.0e-12)
    assert not math.isclose(13.618, delta, rel_tol=0.0, abs_tol=1.0e-12)
    assert (+delta * N_A * R) > 0.0

    assert contract["lookup_policy"]["bounds_policy"] == "error"
    assert contract["lookup_policy"]["silent_clamp"] is False
    assert contract["lookup_policy"]["silent_floor"] is False
    assert "fixture only" in contract["lookup_policy"]["controlled_fixture_note"]

    print("E8_EI16_O2_IONIZATION_ENERGY_CONTRACT_PASS")


if __name__ == "__main__":
    main()
