"""Compatibility adapter for the JSON-backed Issue46 Jacobian-localization spec."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose.input import MooseInputError
from physics_harness.adapters.moose import petsc_options as po
from physics_harness.adapters.moose.mutation_spec import compile_mutation_spec, load_mutation_json_file
from physics_harness.adapters.moose.mutation_spec.plan import MutationCasePlan, MutationPlan, OperationPlan
from physics_harness.adapters.moose.transforms import TransformError, apply_case_plan

TARGET = 1.0e16
SPEC_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "experiments"
    / "issue46_jacobian_localization.json"
)


@lru_cache(maxsize=1)
def _execution_plan() -> MutationPlan:
    return compile_mutation_spec(load_mutation_json_file(SPEC_PATH))


def _case() -> MutationCasePlan:
    return _execution_plan().case("localization")


def _one_operation(op: str) -> OperationPlan:
    matches = [operation for operation in _case().operations if operation.op == op]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {op!r} operation, found {len(matches)}")
    return matches[0]


def _localization_threshold() -> float:
    value = _one_operation("set_petsc_option").argument_dict().get("value")
    if not isinstance(value, str):
        raise RuntimeError("invalid localization threshold in ExperimentSpec")
    return float(value)


def _dofmap_policy() -> tuple[str, str]:
    operation = _one_operation("insert_child_block")
    args = operation.argument_dict()
    path = args.get("path")
    block = args.get("block")
    if not isinstance(path, str) or not isinstance(block, str):
        raise RuntimeError("invalid DOFMap insertion plan")
    output = path.rsplit("/", 1)[-1]
    match = re.search(r"(?m)^\s*file_base\s*=\s*(\S+)\s*$", block)
    if match is None:
        raise RuntimeError("DOFMap insertion plan is missing file_base")
    return output, match.group(1)


LOCALIZATION_THRESHOLD = _localization_threshold()
DOFMAP_OUTPUT, DOFMAP_FILE_BASE = _dofmap_policy()


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


def instrument_localization(first_linear_text: str) -> tuple[str, dict[str, Any]]:
    try:
        out = apply_case_plan(first_linear_text, _case())
    except TransformError as exc:
        _raise_legacy_compatible(exc)
        raise AssertionError("unreachable")
    return out, {
        "target": TARGET,
        "localization_threshold": LOCALIZATION_THRESHOLD,
        "dofmap_output": DOFMAP_OUTPUT,
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "scaling_policy_changed": False,
        "diagnostic_observability_only": True,
    }
