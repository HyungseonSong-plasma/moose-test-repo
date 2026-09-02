"""R3 master-diagnostic case construction on top of accepted #94/#93 scientific inputs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from experiments.Issue94_r3_electron_diffusion_localization.localization import build_localization_input
from experiments.Issue93_r3_electron_isolation.operator_decomposition import build_case_input as build_issue93_case
from experiments.Issue93_r3_electron_isolation.prepare import ELECTRON_REFERENCE_CASE
from qpx_harness.execution.cases import stage_case, validate_case_references

from .spec import (
    CaseSpec,
    FROZEN_DIFFUSION,
    FROZEN_MOBILITY,
    FROZEN_NEUTRAL_DENSITY,
    PLASMA_BOUNDARIES,
)


class MasterCaseError(RuntimeError):
    pass


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise MasterCaseError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def _block_bounds(text: str, header: str) -> tuple[int, int]:
    start = text.find(header)
    if start < 0:
        raise MasterCaseError(f"missing block header: {header}")
    cursor = start + len(header)
    depth = 1
    lines = text[cursor:].splitlines(keepends=True)
    pos = cursor
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped != "[]" and not stripped.startswith("[../"):
            depth += 1
        elif stripped == "[]":
            depth -= 1
            if depth == 0:
                return start, pos + len(line)
        pos += len(line)
    raise MasterCaseError(f"unterminated block: {header}")


def _edit_block(text: str, header: str, editor) -> str:
    start, end = _block_bounds(text, header)
    block = text[start:end]
    updated = editor(block)
    if updated == block:
        raise MasterCaseError(f"block edit produced no semantic change: {header}")
    return text[:start] + updated + text[end:]


def _set_or_insert(block: str, name: str, value: str) -> str:
    lines = block.splitlines(keepends=True)
    needle = f"{name} ="
    matches = [i for i, line in enumerate(lines) if line.strip().startswith(needle)]
    if len(matches) > 1:
        raise MasterCaseError(f"duplicate parameter {name}")
    if matches:
        indent = lines[matches[0]][: len(lines[matches[0]]) - len(lines[matches[0]].lstrip())]
        lines[matches[0]] = f"{indent}{name} = {value}\n"
        return "".join(lines)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "[]":
            lines.insert(i, f"    {name} = {value}\n")
            return "".join(lines)
    raise MasterCaseError(f"cannot insert parameter {name}")


def _set_variable_parameter(text: str, name: str, value: str) -> str:
    return _edit_block(text, "  [n_e]\n", lambda block: _set_or_insert(block, name, value))


def _set_diffusion_parameter(text: str, name: str, value: str) -> str:
    return _edit_block(text, "  [diffusion]\n", lambda block: _set_or_insert(block, name, value))


def _set_electron_transport_parameter(text: str, name: str, value: str) -> str:
    return _edit_block(text, "  [electron_transport]\n", lambda block: _set_or_insert(block, name, value))


def _replace_electron_transport_type(text: str, new_type: str) -> str:
    def edit(block: str) -> str:
        lines = block.splitlines(keepends=True)
        matches = [i for i, line in enumerate(lines) if line.strip().startswith("type =")]
        if len(matches) != 1:
            raise MasterCaseError(f"electron_transport type matches={len(matches)}")
        indent = lines[matches[0]][: len(lines[matches[0]]) - len(lines[matches[0]].lstrip())]
        lines[matches[0]] = f"{indent}type = {new_type}\n"
        return "".join(lines)
    return _edit_block(text, "  [electron_transport]\n", edit)


def _use_literal_diffusion(text: str, value: str | None = None) -> str:
    coefficient = repr(FROZEN_DIFFUSION) if value is None else value
    return _set_diffusion_parameter(text, "coeff", coefficient)


def _use_generic_ad_transport(text: str) -> str:
    def edit(_block: str) -> str:
        return """  [electron_transport]
    type = ADGenericFunctorMaterial
    prop_names = 'electron_mobility electron_diffusion neutral_number_density'
    prop_values = '{mobility} {diffusion} {neutral_density}'
    block = plasma
  []
""".format(
            mobility=repr(FROZEN_MOBILITY),
            diffusion=repr(FROZEN_DIFFUSION),
            neutral_density=repr(FROZEN_NEUTRAL_DENSITY),
        )
    return _edit_block(text, "  [electron_transport]\n", edit)


def _add_observables(text: str) -> str:
    marker = "[Postprocessors]\n"
    if marker not in text:
        raise MasterCaseError("missing Postprocessors block")
    if "diag_electron_diffusion_min" in text:
        return text
    addition = """  [diag_electron_diffusion_min]\n    type = ADElementExtremeFunctorValue\n    functor = electron_diffusion\n    value_type = min\n    block = plasma\n  []\n  [diag_electron_diffusion_max]\n    type = ADElementExtremeFunctorValue\n    functor = electron_diffusion\n    value_type = max\n    block = plasma\n  []\n  [diag_electron_mobility_min]\n    type = ADElementExtremeFunctorValue\n    functor = electron_mobility\n    value_type = min\n    block = plasma\n  []\n  [diag_electron_mobility_max]\n    type = ADElementExtremeFunctorValue\n    functor = electron_mobility\n    value_type = max\n    block = plasma\n  []\n"""
    return _replace_once(text, marker, marker + addition, "diagnostic observables")


def _transform_value(spec: CaseSpec, name: str, default: str | None = None) -> str | None:
    values = [value for key, value in spec.transforms if key == name]
    if len(values) > 1:
        raise MasterCaseError(f"duplicate transform {name} for {spec.case_id}")
    return values[0] if values else default


def _build_linear_reference_input(spec: CaseSpec) -> str:
    """Build a same-qvt/RZ LinearFVDiffusion reference pair.

    The nonlinear FVDiffusion in the pinned MOOSE build does not expose a
    non-orthogonal-correction switch. LinearFVDiffusion does, so this pair is
    intentionally an independent framework reference, not a production-path
    substitute or remedy proxy.
    """
    reference = (ELECTRON_REFERENCE_CASE / "input.i").read_text()
    mesh_start, mesh_end = _block_bounds(reference, "[Mesh]\n")
    mesh = reference[mesh_start:mesh_end]
    correction = _transform_value(spec, "use_nonorthogonal_correction")
    if correction not in {"true", "false"}:
        raise MasterCaseError(f"{spec.case_id}: invalid non-orthogonal setting {correction!r}")
    return f"""# R3 master diagnostic: {spec.case_id} / {spec.family}
# Independent pinned-MOOSE LinearFVDiffusion reference on the same qvt/RZ/plasma mesh.
{mesh}

[Problem]
  linear_sys_names = 'electron_diag_sys'
[]

[Variables]
  [n_e]
    type = MooseLinearVariableFVReal
    solver_sys = 'electron_diag_sys'
    initial_condition = 1e16
    block = plasma
  []
[]

[LinearFVKernels]
  [time]
    type = LinearFVTimeDerivative
    variable = n_e
    block = plasma
  []
  [diffusion]
    type = LinearFVDiffusion
    variable = n_e
    diffusion_coeff = {FROZEN_DIFFUSION!r}
    use_nonorthogonal_correction = {correction}
    block = plasma
  []
[]

[Postprocessors]
  [n_avg]
    type = ElementAverageValue
    variable = n_e
    block = plasma
  []
  [n_min]
    type = ElementExtremeValue
    variable = n_e
    value_type = min
    block = plasma
  []
  [n_max]
    type = ElementExtremeValue
    variable = n_e
    value_type = max
    block = plasma
  []
[]

[Executioner]
  type = Transient
  system_names = electron_diag_sys
  scheme = implicit-euler
  start_time = 0
  dt = 1e-8
  num_steps = 1
  l_tol = 1e-12
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
"""


def apply_transform(text: str, name: str, value: str) -> str:
    if name in {"two_term_boundary_expansion", "face_interp_method", "cache_cell_gradients"}:
        return _set_variable_parameter(text, name, value)
    if name == "variable_type":
        return _set_variable_parameter(text, "type", value)
    if name == "initial_n_e":
        return _set_variable_parameter(text, "initial_condition", value)
    if name in {"coeff_interp_method", "variable_interp_method"}:
        return _set_diffusion_parameter(text, name, value)
    if name == "literal_diffusion":
        return _use_literal_diffusion(text, value)
    if name == "boundaries_to_avoid":
        joined = " ".join(PLASMA_BOUNDARIES) if value == "all" else value
        return _set_diffusion_parameter(text, name, f"'{joined}'")
    if name == "material_ad":
        if value != "false":
            raise MasterCaseError(f"unsupported material_ad value: {value}")
        return _replace_electron_transport_type(text, "GenericFunctorMaterial")
    if name == "qpx_mean_energy":
        return _set_electron_transport_parameter(text, "mean_energy", value)
    if name == "qpx_pressure":
        return _set_electron_transport_parameter(text, "pressure", value)
    if name == "qpx_gas_temperature":
        return _set_electron_transport_parameter(text, "gas_temperature", value)
    if name in {"automatic_scaling", "off_diagonals_in_auto_scaling", "nl_abs_tol"}:
        return _edit_block(text, "[Executioner]\n", lambda block: _set_or_insert(block, name, value))
    if name == "use_nonorthogonal_correction":
        raise MasterCaseError("use_nonorthogonal_correction is only valid for LINEAR_REF cases")
    raise MasterCaseError(f"unknown transform: {name}")


def _initial_n_e(spec: CaseSpec) -> float | None:
    for name, value in spec.transforms:
        if name == "initial_n_e":
            return float(value)
    return None


def _update_expected_n0(target: Path, spec: CaseSpec) -> None:
    n0 = _initial_n_e(spec)
    if n0 is None:
        return
    expected_path = target / "expected.json"
    expected = json.loads(expected_path.read_text())
    expected["n0"] = n0
    expected_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")


def build_case_text(spec: CaseSpec) -> str:
    if spec.base == "LINEAR_REF":
        return _build_linear_reference_input(spec)
    text = build_localization_input(spec.base)
    if spec.base == "L2":
        # #94 L2 replaces the QPX material. Keep all accepted diagnostic
        # observables valid by explicitly providing neutral_number_density too.
        text = _use_generic_ad_transport(text)
    for name, value in spec.transforms:
        text = apply_transform(text, name, value)
    text = _add_observables(text)
    return f"# R3 master diagnostic: {spec.case_id} / {spec.family}\n" + text


def build_r3_proxy_text(spec: CaseSpec, field: str) -> str:
    """Build full-electron R3 E0/Econst counterfactual using an isolated remedy proxy."""
    if field == "E0":
        text = build_issue93_case("C4")
    elif field == "Econst":
        text = build_issue93_case("C0")
    else:
        raise MasterCaseError(f"unknown R3 proxy field: {field}")

    if spec.base == "L1":
        text = _use_literal_diffusion(text)
    elif spec.base == "L2":
        text = _use_generic_ad_transport(text)
    elif spec.base == "LINEAR_REF":
        raise MasterCaseError("LINEAR_REF is a diagnostic reference and cannot be a full-R3 remedy proxy")
    elif spec.base != "L3":
        raise MasterCaseError(f"unsupported R3 remedy proxy base: {spec.base}")

    for name, value in spec.transforms:
        text = apply_transform(text, name, value)
    text = _add_observables(text)
    return f"# R3 remedy proxy: {spec.case_id} / {field}\n" + text


def stage_master_case(
    spec: CaseSpec,
    target: Path,
    *,
    source_case: Path = ELECTRON_REFERENCE_CASE,
    purge_patterns: Iterable[str] = ("input_out*", "*.log", "*.csv", "*.e", "*.exo"),
) -> dict[str, object]:
    text = build_case_text(spec)
    staged = stage_case(
        source_case,
        target,
        input_text=text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=purge_patterns,
    )
    _update_expected_n0(target, spec)
    refs = validate_case_references(target)
    staged["case_id"] = spec.case_id
    staged["family"] = spec.family
    staged["kind"] = spec.kind
    staged["meaning"] = spec.meaning
    staged["referenced_files"] = refs
    return staged


def stage_r3_proxy_case(
    spec: CaseSpec,
    field: str,
    target: Path,
    *,
    source_case: Path = ELECTRON_REFERENCE_CASE,
) -> dict[str, object]:
    text = build_r3_proxy_text(spec, field)
    staged = stage_case(
        source_case,
        target,
        input_text=text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.csv", "*.e", "*.exo"),
    )
    _update_expected_n0(target, spec)
    staged["referenced_files"] = validate_case_references(target)
    staged["case_id"] = spec.case_id
    staged["field"] = field
    return staged
