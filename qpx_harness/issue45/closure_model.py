"""Issue45 constrained quasi-steady model construction."""
from __future__ import annotations

import re

from .. import issue43_fast_relaxation as v5
from ..moose_input import MooseInput
from .constants import (
    C0_TARGET,
    C1_TARGET,
    CONSTRAINT_TYPE,
    DEFAULT_MACRO_ELECTRON_AVG,
    DRIFT_TYPE,
    DT_REFERENCE,
    EXPECTED_DRIFT_BOUNDARIES,
    LAMBDA_VARIABLE,
    MACRO_AVG_POSTPROCESSOR,
    STEPS,
)
from .errors import ElectronInventoryNullspaceError
from .inventory_structure import _ensure_debug_block, _set_or_insert_parameter


def _remove_block(text: str, path: str) -> str:
    span = MooseInput(text).unique(path)
    return text[: span.start] + text[span.end :]


def _replace_block(text: str, path: str, replacement: str) -> str:
    span = MooseInput(text).unique(path)
    payload = replacement.rstrip() + "\n"
    return text[: span.start] + payload + text[span.end :]


def _synthetic_closed_input() -> str:
    boundaries = " ".join(sorted(EXPECTED_DRIFT_BOUNDARIES))
    return f"""[Variables]
  [n_e]
    type = MooseVariableFVReal
  []
  [potential_plasma]
    type = MooseVariableFVReal
  []
[]
[FVKernels]
  [time]
    type = FVTimeKernel
    variable = n_e
  []
  [diffusion]
    type = FVDiffusion
    variable = n_e
  []
  [drift]
    type = {DRIFT_TYPE}
    variable = n_e
    boundaries_to_avoid = '{boundaries}'
  []
  [phi]
    type = FVDiffusion
    variable = potential_plasma
  []
[]
[FVBCs]
  [g0]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_metal
    value = 0
  []
  [g1]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_electrode
    value = 0
  []
  [g2]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_right
    value = 0
  []
  [g3]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = inlet
    value = 0
  []
  [g4]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = outlet
    value = 0
  []
[]
"""


def _synthetic_constrained_input(macro_avg: float = DEFAULT_MACRO_ELECTRON_AVG) -> str:
    base = _synthetic_closed_input().replace(
        "  [time]\n    type = FVTimeKernel\n    variable = n_e\n  []\n", "", 1
    )
    base, _ = MooseInput(base).insert_before_close(
        "Variables",
        f"""  [{LAMBDA_VARIABLE}]
    type = MooseVariableScalar
  []""",
    )
    base, _ = MooseInput(base).insert_before_close(
        "FVKernels",
        f"""  [inventory_constraint]
    type = {CONSTRAINT_TYPE}
    variable = n_e
    lambda = {LAMBDA_VARIABLE}
    phi0 = {MACRO_AVG_POSTPROCESSOR}
    block = plasma
  []""",
    )
    base += f"""
[Postprocessors]
  [{MACRO_AVG_POSTPROCESSOR}]
    type = ConstantPostprocessor
    value = {macro_avg:.17g}
  []
[]
[Executioner]
  type = Steady
  solve_type = NEWTON
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]
[Outputs]
  [out]
    type = CSV
    execute_on = FINAL
  []
  [console]
    type = Console
    execute_on = FINAL
    all_variable_norms = true
  []
[]
[Debug]
  show_var_residual_norms = true
[]
"""
    return base


def _build_constrained_quasisteady_input(
    base_text: str,
    *,
    radial_span: float,
    macro_avg: float,
    runtime_observability: bool = True,
) -> str:
    """Transform the accepted feedback model into the #45 constrained steady candidate."""
    text = v5._build_feedback_v5(
        base_text,
        dt=DT_REFERENCE,
        steps=STEPS,
        radial_span=radial_span,
    )
    text = _remove_block(text, "FVKernels/time")
    text, _ = MooseInput(text).insert_before_close(
        "Variables",
        f"""  [{LAMBDA_VARIABLE}]
    type = MooseVariableScalar
  []""",
    )
    text, _ = MooseInput(text).insert_before_close(
        "Postprocessors",
        f"""  [{MACRO_AVG_POSTPROCESSOR}]
    type = ConstantPostprocessor
    value = {macro_avg:.17g}
    outputs = none
  []""",
    )
    text, _ = MooseInput(text).insert_before_close(
        "FVKernels",
        f"""  [r45_inventory_constraint]
    type = {CONSTRAINT_TYPE}
    variable = n_e
    lambda = {LAMBDA_VARIABLE}
    phi0 = {MACRO_AVG_POSTPROCESSOR}
    block = plasma
  []""",
    )
    text = _replace_block(
        text,
        "Executioner",
        """[Executioner]
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
[]""",
    )
    text = _set_or_insert_parameter(text, "Outputs/out", "execute_on", "FINAL")
    text = _set_or_insert_parameter(text, "Outputs/console", "execute_on", "FINAL")
    if runtime_observability:
        text = _ensure_debug_block(text)
        text = _set_or_insert_parameter(
            text, "Outputs/console", "all_variable_norms", "true"
        )
    MooseInput(text)
    return text


def _normalized_target_text(text: str) -> str:
    path = f"Postprocessors/{MACRO_AVG_POSTPROCESSOR}"
    span = MooseInput(text).unique(path)
    block = text[span.start : span.end]
    normalized, count = re.subn(
        r"(?m)^(\s*value\s*=\s*)[^#\r\n]+",
        r"\1<TARGET>",
        block,
        count=1,
    )
    if count != 1:
        raise ElectronInventoryNullspaceError("failed to normalize macro-average target")
    return text[: span.start] + normalized + text[span.end :]


def _target_only_pair_audit(c0_text: str, c1_text: str) -> dict[str, object]:
    equal = _normalized_target_text(c0_text) == _normalized_target_text(c1_text)
    return {
        "status": "PASS" if equal else "HOLD",
        "class": "TARGET_ONLY_PAIR_PASS" if equal else "PAIR_CONSTRUCTION_MISMATCH",
        "reason": (
            "C0/C1 inputs are byte-identical after normalizing the declared macro electron-average target"
            if equal
            else "C0/C1 differ in construction beyond the declared macro electron-average target"
        ),
    }


def build_synthetic_target_pair() -> tuple[str, str]:
    """Characterization-only C0/C1 pair under the frozen Issue45 targets."""
    return _synthetic_constrained_input(C0_TARGET), _synthetic_constrained_input(C1_TARGET)
