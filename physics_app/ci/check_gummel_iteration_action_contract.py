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
    '"electron_input_file"',
    '"electron_multiapp"',
    '"electron_execution_order_group"',
    '"poisson_input_file"',
    '"poisson_multiapp"',
    '"poisson_execution_order_group"',
    '"electron_density_variable"',
    '"poisson_electron_density_variable"',
    '"poisson_potential_variable"',
    '"electron_potential_variable"',
    '"electron_state_variables"',
    '"electron_to_poisson_source_variables"',
    '"electron_to_poisson_variables"',
    '"poisson_to_electron_source_variables"',
    '"poisson_to_electron_variables"',
    '"DeltaPhiMultiAppConvergence"',
    'params.set<MultiAppName>("from_multi_app") = electron_name;',
    'params.set<MultiAppName>("to_multi_app") = poisson_name;',
    'params.set<MultiAppName>("from_multi_app") = poisson_name;',
    'params.set<MultiAppName>("to_multi_app") = electron_name;',
    'params.set<bool>("execute_after_from_multiapp") = true;',
    'object_prefix + "_shared_n_e"',
    'object_prefix + "_shared_phi"',
    'electron_params.set<unsigned int>("execution_order_group")',
    'poisson_params.set<unsigned int>("execution_order_group")',
)
for token in required:
    assert token in src, token

assert 'syntax.registerActionSyntax("GummelIterationAction", "GummelIteration/*")' in app
assert "class GummelIterationAction : public Action" in hdr
assert "bool usesElectronSubApp() const;" in hdr

# Preferred two-subapp contract: electron first, Poisson second, direct siblings.
assert '"electron_execution_order_group",
      0,' in src
assert '"poisson_execution_order_group",
      1,' in src
assert '"n_e"' in src
assert '"phi"' in src

# Legacy mode remains available when electron_input_file is omitted.
assert 'if (usesElectronSubApp())' in src
assert 'else
    {' in src
assert 'Legacy current-application electron mode requires' in src

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
assert "setMultiAppFixedPointConvergenceName" not in src

print("GUMMEL_ITERATION_ACTION_CONTRACT: PASS")
