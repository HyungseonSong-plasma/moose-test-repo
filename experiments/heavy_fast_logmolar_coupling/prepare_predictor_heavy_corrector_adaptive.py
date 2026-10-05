#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORRECTIONS = int(os.environ.get("CORRECTIONS", "5"))

if CORRECTIONS < 1:
    raise RuntimeError("CORRECTIONS must be >= 1")

# Build the qualified adaptive predictor case first:
#   cycle 1: 0 -> 1 ns
#   cycle 2: 1 -> 10 ns (9 ns step)
# with [energy -> electron+Poisson] x CORRECTIONS at each fast solve.
os.environ["CORRECTIONS"] = str(CORRECTIONS)
subprocess.run(
    ["python3", "prepare_fast_first_adaptive_1ns_9ns.py"],
    cwd=HERE,
    check=True,
    env=os.environ.copy(),
)

parent_path = HERE / "heavy_parent.i"
predictor_fast_path = HERE / "fast_child.i"
predictor_ep_path = HERE / "electron_poisson_stage.i"
corrector_fast_path = HERE / "fast_corrector.i"
corrector_ep_path = HERE / "electron_poisson_corrector_stage.i"

predictor_fast = predictor_fast_path.read_text(encoding="utf-8")
predictor_ep = predictor_ep_path.read_text(encoding="utf-8")
parent = parent_path.read_text(encoding="utf-8")

# Keep predictor and corrector outputs separate for direct endpoint comparison.
predictor_fast = predictor_fast.replace(
    "output_adaptive/energy", "output_predictor_corrector/predictor_energy"
)
predictor_ep = predictor_ep.replace(
    "output_adaptive/electron_poisson", "output_predictor_corrector/predictor_electron_poisson"
)
predictor_fast_path.write_text(predictor_fast, encoding="utf-8")
predictor_ep_path.write_text(predictor_ep, encoding="utf-8")

# A separate corrector MultiApp is essential: it owns its own physical old state.
# At cycle k it advances from F^n to F^(n+1) using the UPDATED heavy state H^(n+1),
# rather than treating the predictor F^(n+1,*) as the old physical state.
corrector_fast = predictor_fast
needle = "input_files = 'electron_poisson_stage.i'"
if needle not in corrector_fast:
    raise RuntimeError("nested predictor electron-Poisson input not found")
corrector_fast = corrector_fast.replace(
    needle, "input_files = 'electron_poisson_corrector_stage.i'", 1
)
corrector_fast = corrector_fast.replace(
    "output_predictor_corrector/predictor_energy",
    "output_predictor_corrector/corrector_energy",
)

corrector_ep = predictor_ep.replace(
    "output_predictor_corrector/predictor_electron_poisson",
    "output_predictor_corrector/corrector_electron_poisson",
)

corrector_fast_path.write_text(corrector_fast, encoding="utf-8")
corrector_ep_path.write_text(corrector_ep, encoding="utf-8")

# Parent-side storage of the ACCEPTED fast endpoint.  These values are initialized
# at F^0, overwritten by the post-heavy corrector at TIMESTEP_END, and injected
# into the predictor before the next physical step.  potential_fast already serves
# as the accepted phi storage and as the field seen by heavy transport.
aux_marker = """  [potential_fast]\n    type = MooseVariableFVReal\n    initial_condition = 0.0\n    block = plasma\n  []\n"""
aux_insert = aux_marker + """  [log_ne_fast_state]\n    type = MooseVariableFVReal\n    initial_condition = -17.913538455038942\n    block = plasma\n  []\n  [log_energy_fast_state]\n    type = MooseVariableFVReal\n    initial_condition = -16.167341364887978\n    block = plasma\n  []\n"""
if aux_marker not in parent:
    raise RuntimeError("parent potential_fast AuxVariable block not found")
parent = parent.replace(aux_marker, aux_insert, 1)

# Add a second fast application that runs only AFTER the parent heavy solve.
old_multiapps = """[MultiApps]\n  [fast_plasma]\n    type = TransientMultiApp\n    input_files = 'fast_child.i'\n    sub_cycling = false\n    interpolate_transfers = false\n    output_sub_cycles = true\n    execute_on = TIMESTEP_BEGIN\n  []\n[]\n"""
new_multiapps = """[MultiApps]\n  [fast_plasma]\n    type = TransientMultiApp\n    input_files = 'fast_child.i'\n    sub_cycling = false\n    interpolate_transfers = false\n    output_sub_cycles = true\n    execute_on = TIMESTEP_BEGIN\n  []\n  [fast_corrector]\n    type = TransientMultiApp\n    input_files = 'fast_corrector.i'\n    sub_cycling = false\n    interpolate_transfers = false\n    output_sub_cycles = true\n    execute_on = TIMESTEP_END\n  []\n[]\n"""
if old_multiapps not in parent:
    raise RuntimeError("adaptive predictor MultiApps block not found")
parent = parent.replace(old_multiapps, new_multiapps, 1)

# At TIMESTEP_BEGIN, synchronize the predictor's current endpoint with the
# previously accepted corrector endpoint, then provide H^n.  Transient stepping
# promotes that synchronized endpoint to the physical old state for the new step.
old_heavy_to_fast = """  [heavy_state_to_fast]\n    type = MultiAppCopyTransfer\n    to_multi_app = fast_plasma\n    source_variable = 'p T_g_snapshot rho_snapshot w_O2_snapshot w_O2s w_O2p w_O w_Om w_Op w_Os'\n    variable = 'p_heavy T_g_heavy rho_heavy_snapshot w_O2_heavy_snapshot w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'\n    execute_on = TIMESTEP_BEGIN\n  []\n"""
new_heavy_to_fast = """  [accepted_fast_and_heavy_to_predictor]\n    type = MultiAppCopyTransfer\n    to_multi_app = fast_plasma\n    source_variable = 'log_ne_fast_state log_energy_fast_state potential_fast p T_g_snapshot rho_snapshot w_O2_snapshot w_O2s w_O2p w_O w_Om w_Op w_Os'\n    variable = 'log_ne log_energy potential p_heavy T_g_heavy rho_heavy_snapshot w_O2_heavy_snapshot w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'\n    execute_on = TIMESTEP_BEGIN\n  []\n"""
if old_heavy_to_fast not in parent:
    raise RuntimeError("heavy_state_to_fast transfer not found")
parent = parent.replace(old_heavy_to_fast, new_heavy_to_fast, 1)

# The corrector receives H^(n+1) after the heavy solve.  It does NOT receive the
# predictor endpoint as its old state.  Because fast_corrector is a distinct
# transient application, its time derivative remains (F^(n+1)-F^n)/dt.
transfer_end_marker = """  [fast_potential_to_heavy]\n    type = MultiAppCopyTransfer\n    from_multi_app = fast_plasma\n    source_variable = potential\n    variable = potential_fast\n    execute_on = TIMESTEP_BEGIN\n  []\n[]\n"""
transfer_end_replacement = """  [fast_potential_to_heavy]\n    type = MultiAppCopyTransfer\n    from_multi_app = fast_plasma\n    source_variable = potential\n    variable = potential_fast\n    execute_on = TIMESTEP_BEGIN\n  []\n  [updated_heavy_to_corrector]\n    type = MultiAppCopyTransfer\n    to_multi_app = fast_corrector\n    source_variable = 'p T_g_snapshot rho_snapshot w_O2_snapshot w_O2s w_O2p w_O w_Om w_Op w_Os'\n    variable = 'p_heavy T_g_heavy rho_heavy_snapshot w_O2_heavy_snapshot w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'\n    execute_on = TIMESTEP_END\n  []\n  [corrected_fast_state_to_parent]\n    type = MultiAppCopyTransfer\n    from_multi_app = fast_corrector\n    source_variable = 'log_ne log_energy potential'\n    variable = 'log_ne_fast_state log_energy_fast_state potential_fast'\n    execute_on = TIMESTEP_END\n  []\n[]\n"""
if transfer_end_marker not in parent:
    raise RuntimeError("predictor potential return transfer terminator not found")
parent = parent.replace(transfer_end_marker, transfer_end_replacement, 1)

parent = parent.replace("output_adaptive/heavy", "output_predictor_corrector/heavy")
parent_path.write_text(parent, encoding="utf-8")

# Structural guards: predictor at begin, corrector at end, both driven by parent dt.
if parent.count("execute_on = TIMESTEP_BEGIN") < 3:
    raise RuntimeError("predictor TIMESTEP_BEGIN coupling was lost")
if parent.count("execute_on = TIMESTEP_END") < 3:
    raise RuntimeError("post-heavy corrector TIMESTEP_END coupling was not installed")
if "input_files = 'fast_corrector.i'" not in parent:
    raise RuntimeError("fast_corrector MultiApp missing")
if "sub_cycling = true" in parent[parent.find("[MultiApps]"):parent.find("[Executioner]")]:
    raise RuntimeError("outer predictor/corrector must not subcycle")

print("prepared predictor-heavy-corrector adaptive diagnostic")
print(f"  fast block corrections per predictor/corrector: {CORRECTIONS}")
print("  cycle 1 dt: 1 ns")
print("  cycle 2 dt: 9 ns")
print("  sequence each cycle: predictor F(H^n) -> heavy H^(n+1) -> corrector F(H^(n+1))")
print("  corrector owns an independent old physical fast state F^n")
print("  corrected fast endpoint is fed into the next cycle predictor")
