"""R3 master-diagnostic case construction on top of accepted #94/#93 scientific inputs."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from experiments.Issue94_r3_electron_diffusion_localization.localization import build_localization_input
from experiments.Issue93_r3_electron_isolation.operator_decomposition import build_case_input as build_issue93_case
from experiments.Issue93_r3_electron_isolation.prepare import ELECTRON_REFERENCE_CASE
from qpx_harness.execution.cases import stage_case, validate_case_references

from .spec import CaseSpec, FROZEN_DIFFUSION, FROZEN_MOBILITY, PLASMA_BOUNDARIES


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


def _use_literal_diffusion(text: str) -> str:
    return _set_diffusion_parameter(text, "coeff", repr(FROZEN_DIFFUSION))


def _use_generic_ad_transport(text: str) -> str:
    def edit(_block: str) -> str:
        return """  [electron_transport]
    type = ADGenericFunctorMaterial
    prop_names = 'electron_mobility electron_diffusion'
    prop_values = '{mobility} {diffusion}'
    block = plasma
  []
""".format(mobility=repr(FROZEN_MOBILITY), diffusion=repr(FROZEN_DIFFUSION))
    return _edit_block(text, "  [electron_transport]\n", edit)


def _add_observables(text: str) -> str:
    marker = "[Postprocessors]\n"
    if marker not in text:
        raise MasterCaseError("missing Postprocessors block")
    if "diag_electron_diffusion_min" in text:
        return text
    addition = """  [diag_electron_diffusion_min]\n    type = ADElementExtremeFunctorValue\n    functor = electron_diffusion\n    value_type = min\n    block = plasma\n  []\n  [diag_electron_diffusion_max]\n    type = ADElementExtremeFunctorValue\n    functor = electron_diffusion\n    value_type = max\n    block = plasma\n  []\n  [diag_electron_mobility_min]\n    type = ADElementExtremeFunctorValue\n    functor = electron_mobility\n    value_type = min\n    block = plasma\n  []\n  [diag_electron_mobility_max]\n    type = ADElementExtremeFunctorValue\n    functor = electron_mobility\n    value_type = max\n    block = plasma\n  []\n"""
    return _replace_once(text, marker, marker + addition, "diagnostic observables")


def apply_transform(text: str, name: str, value: str) -> str:
    if name in {"two_term_boundary_expansion", "face_interp_method", "cache_cell_gradients"}:
        return _set_variable_parameter(text, name, value)
    if name == "variable_type":
        return _set_variable_parameter(text, "type", value)
    if name in {"coeff_interp_method", "variable_interp_method"}:
        return _set_diffusion_parameter(text, name, value)
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
    if name in {"automatic_scaling", "off_diagonals_in_auto_scaling"}:
        return _edit_block(text, "[Executioner]\n", lambda block: _set_or_insert(block, name, value))
    raise MasterCaseError(f"unknown transform: {name}")


def build_case_text(spec: CaseSpec) -> str:
    text = build_localization_input(spec.base)
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
    staged["referenced_files"] = validate_case_references(target)
    staged["case_id"] = spec.case_id
    staged["field"] = field
    return staged
