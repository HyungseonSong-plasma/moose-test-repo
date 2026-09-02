"""Compatibility adapter for the JSON-backed Issue43 coupling diagnostic spec."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp
from qpx_harness.moose.input import MooseInputError
from qpx_harness.petsc import options as po
from qpx_harness.spec import compile_spec, load_json_file
from qpx_harness.spec.plan import CasePlan, ExecutionPlan
from qpx_harness.transforms import TransformError, apply_case_plan

SPEC_PATH = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "experiments"
    / "issue43_coupling_diagnostic.json"
)


@lru_cache(maxsize=1)
def _execution_plan() -> ExecutionPlan:
    return compile_spec(load_json_file(SPEC_PATH))


def _case(case_id: str) -> CasePlan:
    return _execution_plan().case(case_id)


def _case_petsc_flags(case_id: str) -> tuple[str, ...]:
    flags: list[str] = []
    for operation in _case(case_id).operations:
        if operation.op != "add_petsc_flags":
            continue
        value = operation.argument_dict().get("flags")
        if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
            raise RuntimeError(f"invalid add_petsc_flags plan for {case_id!r}")
        flags.extend(value)
    return tuple(flags)


DIAGNOSTIC_PETSC_OPTIONS = _case_petsc_flags("default")
_JACOBIAN_CASE_PETSC_OPTIONS = _case_petsc_flags("jacobian")
JACOBIAN_PETSC_OPTIONS = tuple(
    flag
    for flag in _JACOBIAN_CASE_PETSC_OPTIONS
    if flag not in DIAGNOSTIC_PETSC_OPTIONS
)


def _raise_legacy_compatible(exc: TransformError) -> None:
    cause = exc.__cause__
    if isinstance(
        cause,
        (
            mb.MooseBlockError,
            mp.MooseParameterError,
            po.PetscOptionsError,
            MooseInputError,
        ),
    ):
        raise cause
    raise mb.MooseBlockError(str(exc)) from exc


def instrument_input(
    input_text: str,
    *,
    jacobian_test: bool = False,
) -> tuple[str, dict[str, Any]]:
    case_id = "jacobian" if jacobian_test else "default"
    try:
        text = apply_case_plan(input_text, _case(case_id))
    except TransformError as exc:
        _raise_legacy_compatible(exc)
        raise AssertionError("unreachable")

    required = _case_petsc_flags(case_id)
    return text, {
        "debug_show_var_residual_norms": True,
        "executioner_verbose": True,
        "console_all_variable_norms": True,
        "petsc_options_added": list(required),
        "jacobian_test": jacobian_test,
        "physics_or_numerics_changed": False,
    }
