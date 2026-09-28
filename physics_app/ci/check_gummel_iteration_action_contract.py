#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/actions/GummelIterationAction.C"
HDR = ROOT / "include/actions/GummelIterationAction.h"
APP = ROOT / "src/base/PhysicsApp.C"
MAIN = ROOT / "ci/gummel_two_subapps_main.i"
ELECTRON = ROOT / "ci/gummel_two_subapps_electron.i"
POISSON = ROOT / "ci/gummel_two_subapps_poisson.i"

src = SRC.read_text(encoding="utf-8")
hdr = HDR.read_text(encoding="utf-8")
app = APP.read_text(encoding="utf-8")
main = MAIN.read_text(encoding="utf-8")
electron = ELECTRON.read_text(encoding="utf-8")
poisson = POISSON.read_text(encoding="utf-8")

required = (
    'registerMooseAction("PhysicsApp", GummelIterationAction, "add_multi_app")',
    'registerMooseAction("PhysicsApp", GummelIterationAction, "add_transfer")',
    'registerMooseAction("PhysicsApp", GummelIterationAction, "add_convergence")',
    '"electron_input_file"',
    '"electron_multiapp"',
    '"poisson_input_file"',
    '"poisson_multiapp"',
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
    'object_prefix + "_shared_n_e"',
    'object_prefix + "_shared_phi"',
)
for token in required:
    assert token in src, token

assert 'syntax.registerActionSyntax("GummelIterationAction", "GummelIteration/*")' in app
assert "class GummelIterationAction : public Action" in hdr
assert "bool usesElectronSubApp() const;" in hdr

# Pinned-MOOSE Gummel scheduling contract:
#   TIMESTEP_BEGIN: phi(old) -> electron, then electron solve
#   TIMESTEP_END:   n_e(new) -> Poisson, then Poisson solve
assert 'electron_params.set<ExecFlagEnum>("execute_on") = EXEC_TIMESTEP_BEGIN;' in src
assert 'poisson_params.set<ExecFlagEnum>("execute_on") = EXEC_TIMESTEP_END;' in src
assert '"execute_after_from_multiapp"' not in src
assert '"execution_order_group"' not in src

# Preferred fixture: parent orchestration + two sibling input files.
for token in (
    "electron_input_file = gummel_two_subapps_electron.i",
    "poisson_input_file = gummel_two_subapps_poisson.i",
    "electron_density_variable = n_e",
    "poisson_electron_density_variable = n_e",
    "poisson_potential_variable = phi",
    "electron_potential_variable = phi",
):
    assert token in main, token

assert "solve = false" in main
assert "[n_e]" in electron
assert "[mean_en]" in electron
assert "[phi]" in electron
assert "[phi]" in poisson
assert "[n_e]" in poisson

# Legacy mode remains available when electron_input_file is omitted.
assert "if (usesElectronSubApp())" in src
assert "Legacy current-application electron mode requires" in src

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

# Electron-response approximations remain Poisson-side optional objects.
assert "FVElectronResponseBandedCorrection" not in src
assert "bandwidth" not in src
assert "setMultiAppFixedPointConvergenceName" not in src

print("GUMMEL_ITERATION_ACTION_CONTRACT: PASS")
