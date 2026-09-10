#!/usr/bin/env python3
"""Contract discriminator for #26 E8-I2 EI16 after Standard-MOOSE energy reduction."""

import json
import math
from pathlib import Path

N_A = 6.02214076e23
CONTRACT = Path("docs/development/2026-09-10_issue26_e8_ei16_energy_contract.json")
R2 = Path("docs/development/2026-09-08_issue17_r2_o2_ionization_contract.json")
RATE = Path("physics_app/src/materials/PhysicsElectronImpactIonizationMaterial.C")
PARTICLE = Path("physics_app/src/materials/PhysicsO2IonizationSourceMaterial.C")
RUNTIME = Path("physics_app/ci/check_e8_ei16_energy_runtime.py")
CUSTOM_H = Path("physics_app/include/fvkernels/PhysicsFVElectronReactionEnergySource.h")
CUSTOM_C = Path("physics_app/src/fvkernels/PhysicsFVElectronReactionEnergySource.C")


def main():
    c = json.loads(CONTRACT.read_text())
    r2 = json.loads(R2.read_text())
    rxn = c["reaction"]
    own = c["ownership"]
    std = c["standard_moose_configuration"]
    assert c["schema_version"] == 2
    assert rxn["id"] == "EI16_O2_IONIZATION"
    assert rxn["canonical_progress"] == "R_ion_O2"
    assert rxn["energy_loss_eV_per_event"] == 12.06
    assert rxn["net_electron_particle_stoich"] == 1
    assert own["canonical_rate_owner"] == "PhysicsElectronImpactIonizationMaterial"
    assert own["particle_source_projector"] == "PhysicsO2IonizationSourceMaterial"
    assert own["electron_particle_projector"] == "PhysicsFVElectronReactionSource"
    assert own["energy_projection_owner"] == "FVCoupledForce"
    assert own["energy_projection_owner_kind"] == "STANDARD_MOOSE"
    assert own["all_source_paths_must_consume"] == "R_ion_O2"
    assert own["energy_projection_must_not_recompute_rate"] is True
    assert std["type"] == "FVCoupledForce" and std["v"] == "R_ion_O2"
    coef = -12.06 * N_A / (1e16 * 5.73276)
    assert math.isclose(std["coef_at_frozen_normalization"], coef, rel_tol=1e-15)

    r2ion = r2["reactions"]["EI16_O2_IONIZATION"]
    assert r2ion["shared_progress"] == "R_ion_O2"
    assert r2ion["energy_loss_eV"] == 12.06
    rate = RATE.read_text()
    particle = PARTICLE.read_text()
    runtime = RUNTIME.read_text()
    assert '"R_ion_O2"' in rate
    assert "interpolateStrict" in rate and "strict R2 policy forbids clamp/floor" in rate
    assert '_reaction_progress(getFunctor<ADReal>("reaction_progress"))' in particle
    assert '"electron_ionization_number_source"' in particle
    assert "type = FVCoupledForce" in runtime and "v = R_ion_O2" in runtime
    assert "ENERGY_COEF = -(DELTA_E_EV * N_A / (N_REF * EPSILON_REF_EV))" in runtime
    assert "type = PhysicsFVElectronReactionEnergySource" not in runtime
    assert not CUSTOM_H.exists() and not CUSTOM_C.exists()
    assert c["lookup_policy"]["bounds_policy"] == "error"
    assert c["lookup_policy"]["silent_clamp"] is False
    assert c["lookup_policy"]["silent_floor"] is False
    assert c["nonnegative_progress_guard"]["independent_energy_only_use"] == "FORBIDDEN"
    R = 0.016887027897333
    rhs = -12.06 * N_A * R / (1e16 * 5.73276)
    assert rhs < 0 and -rhs > 0
    assert math.isclose(-rhs, -coef * R, rel_tol=1e-15)
    print("E8_EI16_O2_IONIZATION_ENERGY_CONTRACT_PASS")


if __name__ == "__main__":
    main()
