#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

helper = (ROOT / "include/utils/PhysicsElectronFluxModel.h").read_text()
drift_h = (ROOT / "include/fvkernels/PhysicsFVElectrostaticDrift.h").read_text()
drift_c = (ROOT / "src/fvkernels/PhysicsFVElectrostaticDrift.C").read_text()
log_h = (ROOT / "include/fvkernels/PhysicsFVLogMolarElectronTransport.h").read_text()
log_c = (ROOT / "src/fvkernels/PhysicsFVLogMolarElectronTransport.C").read_text()
joule_c = (ROOT / "src/fvkernels/PhysicsFVElectronEnergyJouleHeating.C").read_text()

assert "transportedState" in helper
assert "driftNormal" in helper
assert "orthogonalDiffusiveFlux" in helper
assert "electronParticleFlux" in helper
assert "electronElectricWork" in helper

assert "_exponential_state" in drift_h
assert "transported_state" in drift_c
assert "PhysicsElectronFluxModel::driftNormal" in drift_c
assert "PhysicsElectronFluxModel::transportedState" in drift_c

# Legacy log-molar drift remains only as a thin compatibility wrapper.
assert "public PhysicsFVElectrostaticDrift" in log_h
assert "ADReal computeQpResidual() override;" not in log_h.split(
    "class PhysicsFVLogMolarElectrostaticDrift", 1
)[1].split("};", 1)[0]
assert 'params.set<MooseEnum>("transported_state") = "exponential";' in log_c
assert "PhysicsElectronFluxModel::orthogonalDiffusiveFlux" in log_c

# Joule heating must consume the common constitutive flux helper.
assert "PhysicsElectronFluxModel::electronElectricWork" in joule_c
assert "mobility * electron_density * (electric_field * electric_field)" not in joule_c

print("ELECTRON_FLUX_UNIFICATION_CONTRACT: PASS")
