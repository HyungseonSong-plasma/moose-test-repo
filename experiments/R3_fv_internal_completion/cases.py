"""Case builders for the one-queue FV internal completion campaign."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from experiments.Issue93_r3_electron_isolation.prepare import ELECTRON_REFERENCE_CASE
from experiments.Issue94_r3_electron_diffusion_localization.localization import build_localization_input
from experiments.R3_electron_master_diagnostic.cases import (
    _block_bounds,
    _edit_block,
    _set_diffusion_parameter,
    _set_or_insert,
    _set_variable_parameter,
)
from qpx_harness.execution.cases import stage_case, validate_case_references

from .spec import CompletionCaseSpec, FROZEN_D


class CompletionCaseError(RuntimeError):
    pass


def _set_executioner_parameter(text: str, name: str, value: str) -> str:
    return _edit_block(text, "[Executioner]\n", lambda block: _set_or_insert(block, name, value))


def _set_problem_parameter(text: str, name: str, value: str) -> str:
    return _edit_block(text, "[Problem]\n", lambda block: _set_or_insert(block, name, value))


def _insert_material_child(text: str, child: str) -> str:
    def edit(block: str) -> str:
        marker = "\n[]"
        pos = block.rfind(marker)
        if pos < 0:
            raise CompletionCaseError("Materials block has no closing token")
        return block[:pos] + "\n" + child.rstrip() + "\n" + block[pos:]
    return _edit_block(text, "[Materials]\n", edit)


def _replace_diffusion_block(text: str, replacement: str) -> str:
    return _edit_block(text, "  [diffusion]\n", lambda _block: replacement)


def _remove_top_level_block(text: str, header: str) -> str:
    if header not in text:
        return text
    start, end = _block_bounds(text, header)
    return text[:start] + text[end:]


def _set_n0(text: str, n0: float) -> str:
    """Set n_e only when the numerical value changes.

    The shared master-case editor intentionally rejects semantic no-ops. Completion
    controls reuse n_e=1e16, so recognize that existing value before invoking it.
    """
    start, end = _block_bounds(text, "  [n_e]\n")
    block = text[start:end]
    current: float | None = None
    for line in block.splitlines():
        if line.strip().startswith("initial_condition ="):
            try:
                current = float(line.split("=", 1)[1].strip())
            except ValueError:
                current = None
            break
    if current == float(n0):
        return text
    return _set_variable_parameter(text, "initial_condition", repr(float(n0)))


def _configure_raw_solver(text: str, nl_abs_tol: float | None) -> str:
    text = _set_executioner_parameter(text, "automatic_scaling", "false")
    text = _set_executioner_parameter(text, "off_diagonals_in_auto_scaling", "false")
    if nl_abs_tol is not None:
        text = _set_executioner_parameter(text, "nl_abs_tol", repr(float(nl_abs_tol)))
    return text


def _build_time_only(spec: CompletionCaseSpec) -> str:
    text = build_localization_input("L0")
    text = _set_n0(text, spec.n0)
    text = _configure_raw_solver(text, spec.nl_abs_tol)
    return text


def _build_full_internal(spec: CompletionCaseSpec) -> str:
    text = build_localization_input("L1")
    text = _set_n0(text, spec.n0)
    text = _set_diffusion_parameter(
        text,
        "boundaries_to_avoid",
        "'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'",
    )
    text = _configure_raw_solver(text, spec.nl_abs_tol)
    return text


def _build_orthogonal(spec: CompletionCaseSpec) -> str:
    text = build_localization_input("L1")
    text = _set_n0(text, spec.n0)
    text = _configure_raw_solver(text, spec.nl_abs_tol)
    text = _insert_material_child(
        text,
        f"""  [diag_orthogonal_diffusivity]
    type = ADGenericConstantMaterial
    prop_names = 'diag_orthogonal_D'
    prop_values = '{FROZEN_D!r}'
    block = plasma
  []""",
    )
    text = _replace_diffusion_block(
        text,
        """  [diffusion]
    type = FVOrthogonalDiffusion
    variable = n_e
    coeff = diag_orthogonal_D
    block = plasma
  []
""",
    )
    return text


def _schedule_line(initial_schedule: bool) -> str:
    return "    execute_on = INITIAL\n" if initial_schedule else ""


def _gradient_aux_sections(*, initial_schedule: bool) -> str:
    schedule = _schedule_line(initial_schedule)
    vpp_schedule = "    execute_on = INITIAL\n" if initial_schedule else ""
    return f"""
[AuxVariables]
  [grad_ad]
    order = CONSTANT
    family = MONOMIAL_VEC
    block = plasma
  []
  [grad_real]
    order = CONSTANT
    family = MONOMIAL_VEC
    block = plasma
  []
  [grad_ad_x]
    order = CONSTANT
    family = MONOMIAL
    block = plasma
  []
  [grad_ad_y]
    order = CONSTANT
    family = MONOMIAL
    block = plasma
  []
  [grad_real_x]
    order = CONSTANT
    family = MONOMIAL
    block = plasma
  []
  [grad_real_y]
    order = CONSTANT
    family = MONOMIAL
    block = plasma
  []
[]

[AuxKernels]
  [measure_grad_ad]
    type = ADFunctorElementalGradientAux
    variable = grad_ad
    functor = n_e
    block = plasma
{schedule}  []
  [measure_grad_real]
    type = FunctorElementalGradientAux
    variable = grad_real
    functor = n_e
    block = plasma
{schedule}  []
  [grad_ad_x]
    type = VectorVariableComponentAux
    variable = grad_ad_x
    vector_variable = grad_ad
    component = x
    block = plasma
{schedule}  []
  [grad_ad_y]
    type = VectorVariableComponentAux
    variable = grad_ad_y
    vector_variable = grad_ad
    component = y
    block = plasma
{schedule}  []
  [grad_real_x]
    type = VectorVariableComponentAux
    variable = grad_real_x
    vector_variable = grad_real
    component = x
    block = plasma
{schedule}  []
  [grad_real_y]
    type = VectorVariableComponentAux
    variable = grad_real_y
    vector_variable = grad_real
    component = y
    block = plasma
{schedule}  []
[]

[VectorPostprocessors]
  [gradient_samples]
    type = ElementValueSampler
    variable = 'grad_ad_x grad_ad_y grad_real_x grad_real_y'
    block = plasma
    sort_by = id
{vpp_schedule}  []
[]
"""


def _assert_gradient_contract(text: str, *, initial_schedule: bool) -> None:
    required = (
        "[Problem]\n",
        "  solve = false\n",
        "[Executioner]\n  type = Steady\n[]",
        "type = ADFunctorElementalGradientAux",
        "type = FunctorElementalGradientAux",
        "type = VectorVariableComponentAux",
        "type = ElementValueSampler",
    )
    missing = [token for token in required if token not in text]
    if missing:
        raise CompletionCaseError(f"gradient contract missing required tokens: {missing}")
    forbidden = (
        "[FVKernels]\n",
        "type = FVTimeKernel",
        "type = FVDiffusion",
        "type = QPXElectronTransportLookupMaterial",
        "[FunctorMaterials]\n",
        "[Postprocessors]\n",
    )
    present = [token for token in forbidden if token in text]
    if present:
        raise CompletionCaseError(f"gradient contract retained unrelated runtime objects: {present}")
    has_initial = "execute_on = INITIAL" in text
    if initial_schedule != has_initial:
        expected = "present" if initial_schedule else "absent"
        raise CompletionCaseError(f"gradient INITIAL schedule must be {expected}")


def _build_gradient(spec: CompletionCaseSpec, *, initial_schedule: bool) -> str:
    """Build a minimal pinned-MOOSE-style gradient measurement input.

    Keep the accepted qvt/RZ mesh, [Materials], and FV n_e variable, but remove
    solve-time/QPX objects that are irrelevant to direct functor-gradient sampling.
    The default path mirrors the pinned MOOSE functor-gradient regression pattern:
    solve=false + Steady + AuxKernels with default scheduling.
    """
    text = build_localization_input("L1")
    text = _set_n0(text, spec.n0)
    text = _set_variable_parameter(
        text,
        "two_term_boundary_expansion",
        "true" if spec.two_term_boundary_expansion else "false",
    )
    for header in ("[FunctorMaterials]\n", "[FVKernels]\n", "[Postprocessors]\n"):
        text = _remove_top_level_block(text, header)
    text = _set_problem_parameter(text, "solve", "false")
    text = _edit_block(text, "[Executioner]\n", lambda _block: "[Executioner]\n  type = Steady\n[]\n")
    text = _edit_block(
        text,
        "[Outputs]\n",
        lambda _block: (
            "[Outputs]\n  csv = true\n  execute_on = INITIAL\n[]\n"
            if initial_schedule
            else "[Outputs]\n  csv = true\n[]\n"
        ),
    )
    marker = "[Executioner]\n"
    if marker not in text:
        raise CompletionCaseError("gradient case missing Executioner block")
    text = text.replace(marker, _gradient_aux_sections(initial_schedule=initial_schedule) + "\n" + marker, 1)
    _assert_gradient_contract(text, initial_schedule=initial_schedule)
    return text


def build_case_text(spec: CompletionCaseSpec) -> str:
    if spec.operator == "time_only":
        text = _build_time_only(spec)
    elif spec.operator == "full_internal":
        text = _build_full_internal(spec)
    elif spec.operator == "orthogonal":
        text = _build_orthogonal(spec)
    elif spec.operator == "gradient":
        text = _build_gradient(spec, initial_schedule=False)
    elif spec.operator == "gradient_initial":
        text = _build_gradient(spec, initial_schedule=True)
    else:
        raise CompletionCaseError(f"unknown operator: {spec.operator}")
    return f"# R3 FV internal completion: {spec.case_id}\n" + text


def _update_expected_n0(target: Path, n0: float) -> None:
    expected_path = target / "expected.json"
    expected = json.loads(expected_path.read_text())
    expected["n0"] = float(n0)
    expected_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")


def stage_completion_case(
    spec: CompletionCaseSpec,
    target: Path,
    *,
    source_case: Path = ELECTRON_REFERENCE_CASE,
    purge_patterns: Iterable[str] = ("input_out*", "*.log", "*.csv", "*.e", "*.exo"),
) -> dict[str, object]:
    staged = stage_case(
        source_case,
        target,
        input_text=build_case_text(spec),
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=purge_patterns,
    )
    _update_expected_n0(target, spec.n0)
    staged["case_id"] = spec.case_id
    staged["mode"] = spec.mode
    staged["operator"] = spec.operator
    staged["meaning"] = spec.meaning
    staged["referenced_files"] = validate_case_references(target)
    return staged
