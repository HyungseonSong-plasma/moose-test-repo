#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/actions/GummelIterationAction.C"
HDR = ROOT / "include/actions/GummelIterationAction.h"
APP = ROOT / "src/base/PhysicsApp.C"

src = SRC.read_text(encoding="utf-8")
hdr = HDR.read_text(encoding="utf-8")
app = APP.read_text(encoding="utf-8")

required = (
    'registerMooseAction("PhysicsApp", GummelIterationAction, "add_multi_app")',
    'registerMooseAction("PhysicsApp", GummelIterationAction, "add_transfer")',
    'registerMooseAction("PhysicsApp", GummelIterationAction, "add_convergence")',
    '"electron_state_variables"',
    '"electron_to_poisson_source_variables"',
    '"electron_to_poisson_variables"',
    '"poisson_to_electron_source_variables"',
    '"poisson_to_electron_variables"',
    '"poisson_input_file"',
    '"poisson_multiapp"',
    '"DeltaPhiMultiAppConvergence"',
)
for token in required:
    assert token in src, token

assert 'syntax.registerActionSyntax("GummelIterationAction", "GummelIteration/*")' in app
assert "class GummelIterationAction : public Action" in hdr

# The orchestration layer must not select an electron closure/model.
for forbidden in (
    '"electron_model"',
    '"drift_diffusion"',
    '"momentum_model"',
    '"energy_model"',
    "FVElectronDrift",
    "ElectronMomentum",
):
    assert forbidden not in src, forbidden

# Electron response remains a Poisson-side optional object, not part of this Action.
assert "FVElectronResponseBandedCorrection" not in src
assert "bandwidth" not in src

print("GUMMEL_ITERATION_ACTION_CONTRACT: PASS")
