#!/usr/bin/env python3
"""Contract discriminator for #26 E8-I1 EI10 after Standard-MOOSE energy reduction."""

import json
import math
from pathlib import Path

N_A = 6.02214076e23
CONTRACT = Path("docs/development/2026-09-10_issue26_e8_ei10_energy_contract.json")
RATE_OWNER = Path("physics_app/src/materials/PhysicsElectronImpactO2sExcitationMaterial.C")
RUNTIME = Path("physics_app/ci/check_e8_ei10_energy_runtime.py")
CUSTOM_H = Path("physics_app/include/fvkernels/PhysicsFVElectronReactionEnergySource.h")
CUSTOM_C = Path("physics_app/src/fvkernels/PhysicsFVElectronReactionEnergySource.C")


def main():
    c = json.loads(CONTRACT.read_text())
    r = c["reaction"]
    own = c["ownership"]
    std = c["standard_moose_configuration"]
    assert c["schema_version"] == 2
    assert c["work_issue"] == 26 and c["controller_issue"] == 176
    assert c["controller_stage"] == "STAGE_4_E8"
    assert r["id"] == "EI10_O2_TO_O2S"
    assert r["canonical_progress"] == "R_O2s"
    assert r["energy_loss_eV_per_event"] == 0.977
    assert r["net_electron_particle_stoich"] == 0
    assert own["canonical_rate_owner"] == "PhysicsElectronImpactO2sExcitationMaterial"
    assert own["energy_projection_owner"] == "FVCoupledForce"
    assert own["energy_projection_owner_kind"] == "STANDARD_MOOSE"
    assert own["energy_projection_must_consume"] == "R_O2s"
    assert own["energy_projection_must_not_recompute_rate"] is True
    assert own["shared_path_required"] is True
    assert std["type"] == "FVCoupledForce" and std["v"] == "R_O2s"
    expected_coef = -0.977 * N_A / (1.0e16 * 5.73276)
    assert math.isclose(std["coef_at_frozen_normalization"], expected_coef, rel_tol=1e-15)

    rate = RATE_OWNER.read_text()
    runtime = RUNTIME.read_text()
    assert 'addFunctorProperty<ADReal>(\n      "R_O2s"' in rate
    assert "K_O2S = 4.71e8" in rate
    assert "type = FVCoupledForce" in runtime
    assert "v = R_O2s" in runtime
    assert "ENERGY_COEF = -(DELTA_E_EV * N_A / (N_REF * EPSILON_REF_EV))" in runtime
    assert "PhysicsFVElectronReactionEnergySource" not in runtime
    assert not CUSTOM_H.exists() and not CUSTOM_C.exists()

    R = 7.8133117564827e-3
    rhs = -0.977 * N_A * R / (1.0e16 * 5.73276)
    residual = -rhs
    assert rhs < 0 < residual
    assert math.isclose(residual, -expected_coef * R, rel_tol=1e-15)
    assert c["nonnegative_progress_guard"]["independent_energy_only_use"] == "FORBIDDEN"
    assert c["identity_guards"]["forbidden_substitute"] == "user_supplied:o2_excitation_9p97"
    print("E8_EI10_INELASTIC_ENERGY_CONTRACT_PASS")


if __name__ == "__main__":
    main()
