"""MOOSE realization of the electron-inventory integral constraint."""
from __future__ import annotations
from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp
from .constants import CONSTRAINT_TYPE, LAMBDA_VARIABLE, MACRO_AVG_POSTPROCESSOR

def _ensure_debug_block(text: str) -> str:
    if not mb.has_block(text, "Debug"):
        return mb.append_top_level_block(text, "[Debug]\n  show_var_residual_norms = true\n[]")
    return mp.upsert_parameter(text, "Debug", "show_var_residual_norms", "true")

def build_constrained_quasisteady_input(feedback_text: str, *, macro_avg: float, runtime_observability: bool = True) -> str:
    text = mb.remove_block(feedback_text, "FVKernels/time")
    text = mb.insert_child_block(text, "Variables", f"""  [{LAMBDA_VARIABLE}]
    type = MooseVariableScalar
  []""")
    text = mb.insert_child_block(text, "Postprocessors", f"""  [{MACRO_AVG_POSTPROCESSOR}]
    type = ConstantPostprocessor
    value = {macro_avg:.17g}
    outputs = none
  []""")
    text = mb.insert_child_block(text, "FVKernels", f"""  [r45_inventory_constraint]
    type = {CONSTRAINT_TYPE}
    variable = n_e
    lambda = {LAMBDA_VARIABLE}
    phi0 = {MACRO_AVG_POSTPROCESSOR}
    block = plasma
  []""")
    text = mb.replace_block(text, "Executioner", """[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_rel_tol = 1e-8
  nl_max_its = 30
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  compute_scaling_once = true
  verbose = true
  petsc_options = '-snes_converged_reason -ksp_converged_reason'
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]""")
    text = mp.upsert_parameter(text, "Outputs/out", "execute_on", "FINAL")
    text = mp.upsert_parameter(text, "Outputs/console", "execute_on", "FINAL")
    if runtime_observability:
        text = _ensure_debug_block(text)
        text = mp.upsert_parameter(text, "Outputs/console", "all_variable_norms", "true")
    return text
