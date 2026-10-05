#!/usr/bin/env python3
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_CORRECTIONS = int(os.environ.get("MAX_CORRECTIONS", "10"))

if MAX_CORRECTIONS < 2:
    raise RuntimeError("MAX_CORRECTIONS must be >= 2")

# Start from the qualified predictor -> heavy -> corrector construction.
# This preserves the independently owned corrector old state F^n.
env = os.environ.copy()
env["CORRECTIONS"] = str(MAX_CORRECTIONS)
subprocess.run(
    ["python3", "prepare_predictor_heavy_corrector_adaptive.py"],
    cwd=HERE,
    check=True,
    env=env,
)

parent_path = HERE / "heavy_parent.i"
predictor_fast_path = HERE / "fast_child.i"
predictor_ep_path = HERE / "electron_poisson_stage.i"
corrector_fast_path = HERE / "fast_corrector.i"
corrector_ep_path = HERE / "electron_poisson_corrector_stage.i"

parent = parent_path.read_text(encoding="utf-8")
predictor_fast = predictor_fast_path.read_text(encoding="utf-8")
predictor_ep = predictor_ep_path.read_text(encoding="utf-8")
corrector_fast = corrector_fast_path.read_text(encoding="utf-8")
corrector_ep = corrector_ep_path.read_text(encoding="utf-8")


def replace_fixed_point_controls(text: str, label: str) -> str:
    pattern = re.compile(
        r"  fixed_point_min_its = \d+\n"
        r"  fixed_point_max_its = \d+\n"
        r"  fixed_point_rel_tol = [^\n]+\n"
        r"  fixed_point_abs_tol = [^\n]+\n"
        r"  accept_on_max_fixed_point_iteration = (?:true|false)\n"
    )
    replacement = (
        "  fixed_point_min_its = 2\n"
        f"  fixed_point_max_its = {MAX_CORRECTIONS}\n"
        "  fixed_point_rel_tol = 5.0e-3\n"
        "  fixed_point_abs_tol = 1.0e-6\n"
        "  accept_on_max_fixed_point_iteration = false\n"
    )
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"{label}: fixed-point control block not found")
    return updated


def replace_child_time_sequence(text: str, label: str) -> str:
    pattern = re.compile(
        r"  start_time = 0\n"
        r"  end_time = 1\.0e-8\n"
        r"  \[TimeStepper\]\n"
        r"    type = TimeSequenceStepper\n"
        r"    time_sequence = '0 1\.0e-9 1\.0e-8'\n"
        r"  \[\]\n"
    )
    replacement = (
        "  start_time = 0\n"
        "  end_time = 2.0e-8\n"
        "  dt = 1.0e-9\n"
        "  dtmin = 2.5e-10\n"
        "  dtmax = 8.0e-9\n"
    )
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"{label}: TimeSequenceStepper block not found")
    return updated


def replace_parent_time_sequence(text: str) -> str:
    pattern = re.compile(
        r"  start_time = 0\n"
        r"  end_time = 1\.0e-8\n"
        r"  \[TimeStepper\]\n"
        r"    type = TimeSequenceStepper\n"
        r"    time_sequence = '0 1\.0e-9 1\.0e-8'\n"
        r"  \[\]\n"
    )
    replacement = (
        "  start_time = 0\n"
        "  end_time = 2.0e-8\n"
        "  dtmin = 2.5e-10\n"
        "  dtmax = 8.0e-9\n"
        "  auto_advance = false\n"
        "  [TimeStepper]\n"
        "    type = PhysicsFastFixedPointAdaptiveDT\n"
        "    predictor_iterations = predictor_fp_iterations\n"
        "    corrector_iterations = corrector_fp_iterations\n"
        "    initial_dt = 1.0e-9\n"
        "    grow_factor = 1.5\n"
        "    shrink_factor = 0.7\n"
        "    grow_below_iterations = 8\n"
        "    shrink_above_iterations = 8\n"
        "    cutback_factor_at_failure = 0.5\n"
        "  []\n"
    )
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError("parent: TimeSequenceStepper block not found")
    return updated


def prepend_aux(text: str, block: str, label: str) -> str:
    marker = "[AuxVariables]\n"
    if marker not in text:
        raise RuntimeError(f"{label}: AuxVariables section not found")
    return text.replace(marker, marker + block, 1)


def add_executioner_predictor(
    text: str, source_variables: str, target_variables: str, label: str
) -> str:
    marker = "  scheme = implicit-euler\n"
    if text.count(marker) != 1:
        raise RuntimeError(f"{label}: expected one implicit-euler scheme marker")
    block = (
        marker
        + "  [Predictor]\n"
        + "    type = PhysicsTransferredSolutionPredictor\n"
        + "    scale = 1.0\n"
        + f"    source_variables = '{source_variables}'\n"
        + f"    target_variables = '{target_variables}'\n"
        + "  []\n"
    )
    return text.replace(marker, block, 1)


# -----------------------------------------------------------------------------
# Fast fixed-point convergence now controls whether the physical step is valid.
# Do not force-accept a non-contracted Gummel iteration.
# -----------------------------------------------------------------------------
predictor_fast = replace_fixed_point_controls(predictor_fast, "predictor fast")
corrector_fast = replace_fixed_point_controls(corrector_fast, "corrector fast")

# Parent owns the physical dt. Children receive the exact parent dt through
# TransientMultiApp(sub_cycling=false), so remove the prescribed 1 ns -> 9 ns
# TimeSequenceStepper from every child.
predictor_fast = replace_child_time_sequence(predictor_fast, "predictor fast")
predictor_ep = replace_child_time_sequence(predictor_ep, "predictor EP")
corrector_fast = replace_child_time_sequence(corrector_fast, "corrector fast")
corrector_ep = replace_child_time_sequence(corrector_ep, "corrector EP")
parent = replace_parent_time_sequence(parent)

# -----------------------------------------------------------------------------
# Predictor endpoint F^(n+1,*) as Newton initial guess for the post-heavy
# corrector, without touching the corrector transient old state F^n.
#
# The energy corrector owns nonlinear log_energy. log_ne and potential are Aux
# there, so they may be copied directly. The nonlinear energy guess is stored in
# an Aux snapshot and injected by PhysicsTransferredSolutionPredictor after
# state advance and immediately before Newton.
# -----------------------------------------------------------------------------
corrector_fast = prepend_aux(
    corrector_fast,
    """  [predictor_log_energy_guess]
    type = MooseVariableFVReal
    initial_condition = -16.167341364887978
    block = plasma
  []
""",
    "corrector fast",
)
corrector_fast = add_executioner_predictor(
    corrector_fast,
    "predictor_log_energy_guess",
    "log_energy",
    "corrector fast",
)

# Nested electron+Poisson owns nonlinear log_ne and potential. Store predictor
# snapshots in Aux variables and inject them through the Predictor hook exactly
# once per physical target time.
corrector_ep = prepend_aux(
    corrector_ep,
    """  [predictor_log_ne_guess]
    type = MooseVariableFVReal
    initial_condition = -17.913538455038942
    block = plasma
  []
  [predictor_potential_guess]
    type = MooseVariableFVReal
    initial_condition = 0.0
    block = plasma
  []
""",
    "corrector EP",
)
corrector_ep = add_executioner_predictor(
    corrector_ep,
    "predictor_log_ne_guess predictor_potential_guess",
    "log_ne potential",
    "corrector EP",
)

# On the first nested EP solve at a physical time, do not overwrite nonlinear
# log_ne/potential before state advance. Send the energy owner's current Aux
# values to predictor snapshots instead. log_energy and heavy fields remain Aux
# and may still be copied directly.
old_ep_transfer = """    source_variable = 'log_ne log_energy potential p_heavy T_g_heavy rho_heavy_snapshot w_O2_heavy_snapshot w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'
    variable = 'log_ne log_energy potential p_heavy T_g_heavy rho_heavy_snapshot w_O2_heavy_snapshot w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'
"""
new_ep_transfer = """    source_variable = 'log_ne log_energy potential p_heavy T_g_heavy rho_heavy_snapshot w_O2_heavy_snapshot w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'
    variable = 'predictor_log_ne_guess log_energy predictor_potential_guess p_heavy T_g_heavy rho_heavy_snapshot w_O2_heavy_snapshot w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'
"""
if corrector_fast.count(old_ep_transfer) != 1:
    raise RuntimeError("corrector nested EP transfer block not found")
corrector_fast = corrector_fast.replace(old_ep_transfer, new_ep_transfer, 1)

# -----------------------------------------------------------------------------
# Parent-side predictor snapshots and fixed-point diagnostics.
# -----------------------------------------------------------------------------
parent = prepend_aux(
    parent,
    """  [predictor_log_ne_guess]
    type = MooseVariableFVReal
    initial_condition = -17.913538455038942
    block = plasma
  []
  [predictor_log_energy_guess]
    type = MooseVariableFVReal
    initial_condition = -16.167341364887978
    block = plasma
  []
  [predictor_potential_guess]
    type = MooseVariableFVReal
    initial_condition = 0.0
    block = plasma
  []
""",
    "parent",
)

pp_marker = "[Postprocessors]\n"
pp_insert = """[Postprocessors]
  [predictor_fp_iterations]
    type = Receiver
    default = 0
  []
  [corrector_fp_iterations]
    type = Receiver
    default = 0
  []
  [dt_used]
    type = TimestepSize
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""
if parent.count(pp_marker) != 1:
    raise RuntimeError("parent Postprocessors section not found")
parent = parent.replace(pp_marker, pp_insert, 1)

# Predictor endpoint is pulled back after the TIMESTEP_BEGIN predictor solve.
potential_transfer = """  [fast_potential_to_heavy]
    type = MultiAppCopyTransfer
    from_multi_app = fast_plasma
    source_variable = potential
    variable = potential_fast
    execute_on = TIMESTEP_BEGIN
  []
"""
potential_plus_guess = potential_transfer + """  [predictor_fast_state_to_parent_guess]
    type = MultiAppCopyTransfer
    from_multi_app = fast_plasma
    source_variable = 'log_ne log_energy potential'
    variable = 'predictor_log_ne_guess predictor_log_energy_guess predictor_potential_guess'
    execute_on = TIMESTEP_BEGIN
  []
  [predictor_fp_iterations_to_parent]
    type = MultiAppPostprocessorTransfer
    from_multi_app = fast_plasma
    from_postprocessor = fixed_point_iterations
    to_postprocessor = predictor_fp_iterations
    reduction_type = maximum
    execute_on = TIMESTEP_BEGIN
  []
"""
if parent.count(potential_transfer) != 1:
    raise RuntimeError("predictor potential transfer not found")
parent = parent.replace(potential_transfer, potential_plus_guess, 1)

# At TIMESTEP_END, updated H^(n+1) and predictor F^(n+1,*) are sent to the
# independent corrector. Only Aux fields are directly overwritten.
old_heavy_to_corrector = """  [updated_heavy_to_corrector]
    type = MultiAppCopyTransfer
    to_multi_app = fast_corrector
    source_variable = 'p T_g_snapshot rho_snapshot w_O2_snapshot w_O2s w_O2p w_O w_Om w_Op w_Os'
    variable = 'p_heavy T_g_heavy rho_heavy_snapshot w_O2_heavy_snapshot w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'
    execute_on = TIMESTEP_END
  []
"""
new_heavy_to_corrector = """  [updated_heavy_and_predictor_guess_to_corrector]
    type = MultiAppCopyTransfer
    to_multi_app = fast_corrector
    source_variable = 'predictor_log_ne_guess predictor_log_energy_guess predictor_potential_guess p T_g_snapshot rho_snapshot w_O2_snapshot w_O2s w_O2p w_O w_Om w_Op w_Os'
    variable = 'log_ne predictor_log_energy_guess potential p_heavy T_g_heavy rho_heavy_snapshot w_O2_heavy_snapshot w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'
    execute_on = TIMESTEP_END
  []
"""
if parent.count(old_heavy_to_corrector) != 1:
    raise RuntimeError("updated-heavy-to-corrector transfer not found")
parent = parent.replace(old_heavy_to_corrector, new_heavy_to_corrector, 1)

corrected_state_transfer = """  [corrected_fast_state_to_parent]
    type = MultiAppCopyTransfer
    from_multi_app = fast_corrector
    source_variable = 'log_ne log_energy potential'
    variable = 'log_ne_fast_state log_energy_fast_state potential_fast'
    execute_on = TIMESTEP_END
  []
"""
corrected_state_plus_fp = corrected_state_transfer + """  [corrector_fp_iterations_to_parent]
    type = MultiAppPostprocessorTransfer
    from_multi_app = fast_corrector
    from_postprocessor = fixed_point_iterations
    to_postprocessor = corrector_fp_iterations
    reduction_type = maximum
    execute_on = TIMESTEP_END
  []
"""
if parent.count(corrected_state_transfer) != 1:
    raise RuntimeError("corrected fast-state transfer not found")
parent = parent.replace(corrected_state_transfer, corrected_state_plus_fp, 1)

# Separate outputs for predictor/corrector and retain all accepted endpoint fields.
predictor_fast = predictor_fast.replace(
    "output_predictor_corrector/predictor_energy",
    "output_adaptive_fp/predictor_energy",
)
predictor_ep = predictor_ep.replace(
    "output_predictor_corrector/predictor_electron_poisson",
    "output_adaptive_fp/predictor_electron_poisson",
)
corrector_fast = corrector_fast.replace(
    "output_predictor_corrector/corrector_energy",
    "output_adaptive_fp/corrector_energy",
)
corrector_ep = corrector_ep.replace(
    "output_predictor_corrector/corrector_electron_poisson",
    "output_adaptive_fp/corrector_electron_poisson",
)
parent = parent.replace(
    "output_predictor_corrector/heavy",
    "output_adaptive_fp/heavy",
)

# Structural guards.
for label, text in (
    ("predictor fast", predictor_fast),
    ("corrector fast", corrector_fast),
):
    if "accept_on_max_fixed_point_iteration = true" in text:
        raise RuntimeError(f"{label}: forced fixed-point acceptance survived")
    if f"fixed_point_max_its = {MAX_CORRECTIONS}" not in text:
        raise RuntimeError(f"{label}: adaptive fixed-point max not installed")

if corrector_fast.count("PhysicsTransferredSolutionPredictor") != 1:
    raise RuntimeError("energy corrector predictor missing")
if corrector_ep.count("PhysicsTransferredSolutionPredictor") != 1:
    raise RuntimeError("electron-Poisson corrector predictor missing")
if "\n    variable = 'log_ne log_energy potential p_heavy" in corrector_fast:
    raise RuntimeError("corrector EP still directly overwrites nonlinear guess variables")
if "type = PhysicsFastFixedPointAdaptiveDT" not in parent:
    raise RuntimeError("parent adaptive TimeStepper missing")
if "auto_advance = false" not in parent:
    raise RuntimeError("parent must reject failed child solves")

predictor_fast_path.write_text(predictor_fast, encoding="utf-8")
predictor_ep_path.write_text(predictor_ep, encoding="utf-8")
corrector_fast_path.write_text(corrector_fast, encoding="utf-8")
corrector_ep_path.write_text(corrector_ep, encoding="utf-8")
parent_path.write_text(parent, encoding="utf-8")

print("prepared predictor-heavy-corrector adaptive-dt diagnostic")
print(f"  fast fixed-point max corrections: {MAX_CORRECTIONS}")
print("  fixed-point convergence: rel=5e-3, abs=1e-6, min iterations=2")
print("  corrector Newton initial guess: predictor F^(n+1,*)")
print("  corrector old physical state remains F^n")
print("  physical dt: initial=1 ns, min=0.25 ns, max=8 ns")
print("  accepted-step rule: <8 FP its => x1.5; 8 => hold; >8 => x0.7")
print("  failed-step rule: x0.5 and retry")
print("  parent auto_advance=false so failed fast solves reject the physical step")
