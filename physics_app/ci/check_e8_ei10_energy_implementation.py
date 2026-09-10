#!/usr/bin/env python3
"""Static implementation discriminator for the standard-MOOSE #26 E8-I1 energy projection."""

import json
import math
from pathlib import Path

N_A = 6.02214076e23
CONTRACT = Path("docs/development/2026-09-10_issue26_e8_ei10_energy_contract.json")
RUNTIME = Path("physics_app/ci/check_e8_ei10_energy_runtime.py")
AB = Path("physics_app/ci/check_standard_moose_energy_projection.py")
RATE = Path("physics_app/src/materials/PhysicsElectronImpactO2sExcitationMaterial.C")
CUSTOM_H = Path("physics_app/include/fvkernels/PhysicsFVElectronReactionEnergySource.h")
CUSTOM_C = Path("physics_app/src/fvkernels/PhysicsFVElectronReactionEnergySource.C")


def main():
    c = json.loads(CONTRACT.read_text())
    runtime = RUNTIME.read_text()
    ab = AB.read_text()
    rate = RATE.read_text()
    assert c["ownership"]["energy_projection_owner"] == "FVCoupledForce"
    assert c["ownership"]["energy_projection_owner_kind"] == "STANDARD_MOOSE"
    assert not CUSTOM_H.exists() and not CUSTOM_C.exists()
    assert "type = FVCoupledForce" in runtime and "v = R_O2s" in runtime
    assert "PhysicsFVElectronReactionEnergySource" not in runtime
    assert "custom_energy_projector_instantiated" in ab
    assert '"FVCoupledForce"' in ab
    assert 'addFunctorProperty<ADReal>(\n      "R_O2s"' in rate
    assert "K_O2S = 4.71e8" in rate
    coef = -0.977 * N_A / (1e16 * 5.73276)
    assert math.isclose(c["standard_moose_configuration"]["coef_at_frozen_normalization"], coef, rel_tol=1e-15)
    assert coef < 0
    print("E8_EI10_INELASTIC_ENERGY_IMPLEMENTATION_PASS")


if __name__ == "__main__":
    main()
