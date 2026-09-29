#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/actions/GummelIterationAction.C"
HDR = ROOT / "include/actions/GummelIterationAction.h"
APP = ROOT / "src/base/PhysicsApp.C"
MAIN = ROOT / "ci/gummel_two_subapps_main.i"
ELECTRON = ROOT / "ci/gummel_two_subapps_electron.i"
POISSON = ROOT / "ci/gummel_two_subapps_poisson.i"
HEAVY_MAIN = ROOT / "ci/gummel_plasma_closures_heavy_main.i"
DRIVER = ROOT / "ci/gummel_plasma_closures_driver.i"
HEAVY_ELECTRON = ROOT / "ci/gummel_plasma_closures_heavy_electron.i"
HEAVY_POISSON = ROOT / "ci/gummel_plasma_closures_heavy_poisson.i"

src = SRC.read_text(encoding="utf-8")
hdr = HDR.read_text(encoding="utf-8")
app = APP.read_text(encoding="utf-8")
main = MAIN.read_text(encoding="utf-8")
electron = ELECTRON.read_text(encoding="utf-8")
poisson = POISSON.read_text(encoding="utf-8")
heavy_main = HEAVY_MAIN.read_text(encoding="utf-8")
driver = DRIVER.read_text(encoding="utf-8")
heavy_electron = HEAVY_ELECTRON.read_text(encoding="utf-8")
heavy_poisson = HEAVY_POISSON.read_text(encoding="utf-8")

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
    '"potential_transfer_mode"',
    '"parent_potential_variable"',
    '"electron_to_poisson_source_variables"',
    '"electron_to_poisson_variables"',
    '"poisson_to_electron_source_variables"',
    '"poisson_to_electron_variables"',
    '"parent_to_electron_source_variables"',
    '"parent_to_electron_variables"',
    '"electron_to_parent_source_variables"',
    '"electron_to_parent_variables"',
    '"parent_to_poisson_source_variables"',
    '"parent_to_poisson_variables"',
    '"poisson_to_parent_source_variables"',
    '"poisson_to_parent_variables"',
    '"DeltaPhiMultiAppConvergence"',
    'params.set<MultiAppName>("from_multi_app") = electron_name;',
    'params.set<MultiAppName>("to_multi_app") = poisson_name;',
    'params.set<MultiAppName>("from_multi_app") = poisson_name;',
    'params.set<MultiAppName>("to_multi_app") = electron_name;',
    'object_prefix + "_shared_n_e"',
    'object_prefix + "_shared_phi"',
    'object_prefix + "_shared_phi_parent_to_electron"',
    'object_prefix + "_shared_phi_poisson_to_parent"',
    'object_prefix + "_convergence_phi_to_electron"',
    'EXEC_MULTIAPP_FIXED_POINT_CONVERGENCE',
    '"check_multiapp_execute_on"',
    '"residual_multiapp"',
    'object_prefix + "_parent_to_electron_"',
    'object_prefix + "_electron_to_parent_"',
    'object_prefix + "_parent_to_poisson_"',
    'object_prefix + "_poisson_to_parent_"',
)
for token in required:
    assert token in src, token

assert 'syntax.registerActionSyntax("GummelIterationAction", "GummelIteration/*")' in app
assert "class GummelIterationAction : public Action" in hdr
assert "bool usesElectronSubApp() const;" in hdr

# Dead descriptive/configuration-only API must stay retired. MultiApp type is a
# qualified architectural invariant, not a user-selectable Gummel option.
for forbidden in (
    '"electron_state_variables"',
    '"electron_multiapp_type"',
    '"poisson_multiapp_type"',
    '"poisson_transformed_variables"',
):
    assert forbidden not in src, forbidden

# no_restore is retired as a user option but retained as a fixed orchestration
# invariant on both transient sub-applications.
assert 'params.addParam<bool>(\n      "no_restore"' not in src
assert 'getParam<bool>("no_restore")' not in src
assert 'const std::string electron_type = "TransientMultiApp";' in src
assert 'const std::string poisson_type = "TransientMultiApp";' in src
assert 'electron_params.set<bool>("no_restore") = true;' in src
assert 'poisson_params.set<bool>("no_restore") = true;' in src
assert 'poisson_params.set<std::vector<std::string>>("transformed_variables") =' in src
assert '{getParam<VariableName>("poisson_potential_variable")};' in src

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
):
    assert token in main, token

# The fixture intentionally relies on the qualified core-name/default contract.
for redundant in (
    "electron_multiapp = electron",
    "electron_density_variable = n_e",
    "poisson_electron_density_variable = n_e",
    "poisson_potential_variable = phi",
    "electron_potential_variable = phi",
    "no_restore = true",
    "poisson_transformed_variables",
):
    assert redundant not in main, redundant

assert "solve = false" in main
assert "[n_e]" in electron
assert "[mean_en]" in electron
assert "[phi]" in electron
assert "[phi]" in poisson
assert "[n_e]" in poisson

# Frozen-heavy nested composition fixture.
for token in (
    "role = heavy_transport",
    "input_files = 'gummel_plasma_closures_driver.i'",
    "type = MultiAppCopyTransfer",
    "to_multi_app = gummel_driver",
    "heavy_transport_data_file = plasma_closures_oxygen_transport.txt",
    "heavy_species = 'O2 O2s O2p O Om Op Os'",
    "heavy_mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'",
    "source_variable = 'T_g p_gas rho w_O2p w_Om w_Op'",
    "variable = 'T_g_frozen p_gas_frozen rho_frozen w_O2p_frozen w_Om_frozen w_Op_frozen'",
    "from_multi_app = gummel_driver",
    "source_variable = 'n_e_converged T_e_converged'",
    "variable = 'n_e_from_gummel T_e_from_gummel'",
):
    assert token in heavy_main, token

# The Gummel Action now lives in a dedicated solve=false driver. Heavy state is
# represented only by frozen snapshot AuxVariables inside this inner problem.
for token in (
    "solve = false",
    "[T_g_frozen]",
    "[p_gas_frozen]",
    "[rho_frozen]",
    "[w_O2p_frozen]",
    "[w_Om_frozen]",
    "[w_Op_frozen]",
    "[n_e_converged]",
    "[T_e_converged]",
    "[phi_converged]",
    "electron_input_file = gummel_plasma_closures_heavy_electron.i",
    "poisson_input_file = gummel_plasma_closures_heavy_poisson.i",
    "parent_to_electron_source_variables = 'T_g_frozen p_gas_frozen'",
    "electron_to_parent_source_variables = 'n_e T_e_export'",
    "parent_to_poisson_source_variables = 'rho_frozen w_O2p_frozen w_Om_frozen w_Op_frozen'",
    "potential_transfer_mode = through_parent",
    "parent_potential_variable = phi_converged",
    "fixed_point_algorithm = steffensen",
    "transformed_variables = 'phi_converged'",
    "fixed_point_max_its = 3000",
):
    assert token in driver, token

assert "[PlasmaClosures]" not in driver
assert "role = heavy_transport" not in driver
assert "[GummelIteration]" not in heavy_main
assert "[phi_from_gummel]" not in heavy_main
assert "electron_multiapp = electron" not in driver
assert "electron_density_variable = n_e" not in driver
assert "poisson_electron_density_variable = n_e" not in driver
assert "poisson_potential_variable = phi" not in driver
assert "electron_potential_variable = phi" not in driver
assert "electron_to_poisson_source_variables = 'mean_en'" not in driver
assert "electron_to_poisson_variables = 'mean_en'" not in driver
assert "no_restore = true" not in driver
assert "poisson_transformed_variables" not in driver

for token in (
    "role = electron",
    "electron_number_density = n_e",
    "electron_energy_density = mean_en",
    "gas_pressure = p_gas_from_heavy",
    "gas_temperature = T_g_from_heavy",
    "functor = electron_temperature_K",
):
    assert token in heavy_electron, token

assert "[mean_en]" not in heavy_poisson

for token in (
    "role = electrostatic_charge",
    "mixture_density = rho_from_heavy",
    "electron_number_density = n_e",
    "charged_species_ids = 'O2p Om Op'",
    "charged_species_mass_fractions = 'w_O2p_from_heavy w_Om_from_heavy w_Op_from_heavy'",
    "charged_species_molar_masses = '0.032 0.016 0.016'",
    "charged_species_charge_numbers = '1 -1 1'",
):
    assert token in heavy_poisson, token

# Parent-state maps are intentionally sibling-mode-only.
assert "Parent-state mappings are only valid in two-sub-application sibling mode." in src

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

# A solve=false driver cannot use its own zero nonlinear residual as the
# qualified fixed-point residual. Through-parent convergence delegates that
# criterion to the electron child after syncing the latest raw Poisson phi.
assert 'params.set<MultiAppName>("residual_multiapp")' in src
assert 'getParam<MultiAppName>("electron_multiapp")' in src

print("GUMMEL_ITERATION_ACTION_CONTRACT: PASS")
