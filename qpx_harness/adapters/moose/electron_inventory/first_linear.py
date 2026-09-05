"""MOOSE instrumentation for the bounded electron-inventory first-linear diagnostic."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from typing import Any
from qpx_harness.moose import parameters as mp
from qpx_harness.petsc import options as po
from qpx_harness.adapters.moose.mutation_spec import compile_mutation_spec, load_mutation_json_file
from qpx_harness.adapters.moose.mutation_spec.plan import MutationCasePlan, MutationPlan
from qpx_harness.transforms import TransformError, apply_case_plan
ISSUE = 45
TARGET = 1.0e16
SPEC_PATH = Path(__file__).resolve().parents[3] / "specs" / "experiments" / "issue45_first_linear.json"
class Issue45FirstLinearError(RuntimeError):
    pass
@lru_cache(maxsize=1)
def _execution_plan() -> MutationPlan:
    return compile_mutation_spec(load_mutation_json_file(SPEC_PATH))


def _case() -> MutationCasePlan:
    return _execution_plan().case("first_linear")


def _parameter_value(name: str) -> str:
    values = [
        operation.argument_dict().get("value")
        for operation in _case().operations
        if operation.op == "set_parameter"
        and operation.argument_dict().get("path") == "Executioner"
        and operation.argument_dict().get("name") == name
    ]
    if len(values) != 1 or not isinstance(values[0], str):
        raise RuntimeError(f"invalid Issue45 first-linear parameter plan for {name!r}")
    return values[0]


def _flag_groups() -> tuple[tuple[str, ...], ...]:
    groups: list[tuple[str, ...]] = []
    for operation in _case().operations:
        if operation.op != "add_petsc_flags":
            continue
        flags = operation.argument_dict().get("flags")
        if not isinstance(flags, tuple) or not all(isinstance(flag, str) for flag in flags):
            raise RuntimeError("invalid Issue45 first-linear PETSc flag plan")
        groups.append(flags)
    if len(groups) != 2:
        raise RuntimeError(f"expected two Issue45 PETSc flag groups, found {len(groups)}")
    return tuple(groups)


DIAGNOSTIC_NL_MAX_ITS = int(_parameter_value("nl_max_its"))
REQUIRED_EXISTING_OPTIONS, FIRST_LINEAR_PETSC_OPTIONS = _flag_groups()


def _raise_legacy_compatible(exc: TransformError) -> None:
    cause = exc.__cause__
    if isinstance(cause, (mp.MooseParameterError, po.PetscOptionsError)):
        raise cause
    raise Issue45FirstLinearError(str(exc)) from exc


def instrument_first_linear(text: str) -> tuple[str, dict[str, Any]]:
    try:
        out = apply_case_plan(text, _case())
    except TransformError as exc:
        _raise_legacy_compatible(exc)
        raise AssertionError("unreachable")
    return out, {
        "target": TARGET,
        "diagnostic_nl_max_its": DIAGNOSTIC_NL_MAX_ITS,
        "petsc_options_added": list(FIRST_LINEAR_PETSC_OPTIONS),
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "diagnostic_horizon_changed": True,
    }
