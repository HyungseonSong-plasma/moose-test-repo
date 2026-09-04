"""MOOSE target realization boundary for solver-independent ExecutionPlan.

This adapter owns MOOSE spelling only. Scientific meaning remains upstream.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Mapping

from qpx_harness.execution.plan import ExecutionCase, ExecutionPlan


class MooseLoweringError(ValueError):
    pass


@dataclass(frozen=True)
class MooseAssignment:
    path: str
    name: str
    value: str


@dataclass(frozen=True)
class MooseBlock:
    path: str
    type_name: str | None = None
    parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class MooseCaseIR:
    case_id: str
    action_id: str
    model: str | None = None
    blocks: tuple[MooseBlock, ...] = ()
    assignments: tuple[MooseAssignment, ...] = ()
    required_observations: tuple[str, ...] = ()


@dataclass(frozen=True)
class MooseTargetIR:
    source_plan_id: str
    cases: tuple[MooseCaseIR, ...]
    model: str | None = None
    execution_bounds: tuple[tuple[str, Any], ...] = ()


CaseLowerer = Callable[[ExecutionCase], MooseCaseIR]
BuiltinCaseLowerer = Callable[
    [ExecutionCase, str | None, tuple[tuple[str, Any], ...]], MooseCaseIR
]

_ELEMENTARY_CHARGE_C = 1.602176634e-19
_ENERGY_REFERENCE_EV = 5.73276
_ENERGY_VARIABLE = "n_epsilon"
_ENERGY_TIME_KERNEL = "n_epsilon_time"
_ENERGY_DENSITY_EV_FUNCTOR = "n_epsilon_physical_eV_m3"
_ENERGY_DENSITY_J_FUNCTOR = "electron_energy_density_J_m3"
_MEAN_EN_SOLVED_FUNCTOR = "mean_en_solved"
_ENERGY_PROFILE_FUNCTION = "qpx_energy_initial_profile"
_ENERGY_PROFILE_IC = "qpx_n_epsilon_ic"
_ENERGY_DIFFUSIVITY_MATERIAL = "qpx_energy_diffusivity"
_ENERGY_DIFFUSION_KERNEL = "qpx_n_epsilon_diffusion"
_ENERGY_INVENTORY_PP = "electron_energy_inventory_J"
_ENERGY_NORM_AVG_PP = "n_epsilon_avg"
_ENERGY_NORM_MIN_PP = "n_epsilon_min"
_ENERGY_NORM_MAX_PP = "n_epsilon_max"
_MEAN_EN_AVG_PP = "mean_en_solved_avg"
_MEAN_EN_MIN_PP = "mean_en_solved_min"
_MEAN_EN_MAX_PP = "mean_en_solved_max"
_LOCALIZED_BUMP_EXPRESSION = (
    "1.0 + 0.5*exp(-800.0*(x-0.12)^2 - 80.0*(y-0.22)^2)"
)


def _parameter(case: ExecutionCase, name: str) -> Any:
    values = dict(case.parameters)
    if name not in values:
        raise MooseLoweringError(
            f"case {case.case_id!r} requires semantic parameter {name!r}"
        )
    return values[name]


def _execution_assignments(
    execution_bounds: tuple[tuple[str, Any], ...],
) -> tuple[MooseAssignment, ...]:
    bounds = dict(execution_bounds)
    result: list[MooseAssignment] = []
    if "max_steps" in bounds:
        value = int(bounds["max_steps"])
        if value <= 0:
            raise MooseLoweringError("execution bound max_steps must be positive")
        result.append(MooseAssignment("Executioner", "num_steps", str(value)))
    for semantic_name, moose_name in (("dt", "dt"), ("end_time", "end_time")):
        if semantic_name in bounds:
            value = float(bounds[semantic_name])
            if not math.isfinite(value) or value <= 0.0:
                raise MooseLoweringError(
                    f"execution bound {semantic_name} must be finite and positive"
                )
            result.append(
                MooseAssignment("Executioner", moose_name, f"{value:.17g}")
            )
    return tuple(result)


def _energy_bridge_blocks() -> tuple[MooseBlock, ...]:
    energy_scale_ev = f"${{n_e_value}}*{_ENERGY_REFERENCE_EV:.17g}"
    energy_scale_j = (
        f"${{n_e_value}}*{_ENERGY_REFERENCE_EV:.17g}*{_ELEMENTARY_CHARGE_C:.17g}"
    )
    return (
        MooseBlock(
            path=f"FunctorMaterials/{_ENERGY_DENSITY_EV_FUNCTOR}",
            type_name="ADParsedFunctorMaterial",
            parameters=(
                ("property_name", _ENERGY_DENSITY_EV_FUNCTOR),
                ("functor_names", f"'{_ENERGY_VARIABLE}'"),
                ("functor_symbols", "'eps_hat'"),
                ("expression", f"'{energy_scale_ev}*eps_hat'"),
                ("block", "plasma"),
            ),
        ),
        MooseBlock(
            path=f"FunctorMaterials/{_ENERGY_DENSITY_J_FUNCTOR}",
            type_name="ADParsedFunctorMaterial",
            parameters=(
                ("property_name", _ENERGY_DENSITY_J_FUNCTOR),
                ("functor_names", f"'{_ENERGY_VARIABLE}'"),
                ("functor_symbols", "'eps_hat'"),
                ("expression", f"'{energy_scale_j}*eps_hat'"),
                ("block", "plasma"),
            ),
        ),
        MooseBlock(
            path=f"FunctorMaterials/{_MEAN_EN_SOLVED_FUNCTOR}",
            type_name="ADParsedFunctorMaterial",
            parameters=(
                ("property_name", _MEAN_EN_SOLVED_FUNCTOR),
                ("functor_names", f"'{_ENERGY_VARIABLE} n_e'"),
                ("functor_symbols", "'eps_hat ne_hat'"),
                ("expression", f"'{_ENERGY_REFERENCE_EV:.17g}*eps_hat/ne_hat'"),
                ("block", "plasma"),
            ),
        ),
    )


def _observation_blocks(observations: tuple[str, ...]) -> tuple[MooseBlock, ...]:
    blocks: list[MooseBlock] = []
    for observation in observations:
        if observation == "energy_inventory":
            blocks.append(
                MooseBlock(
                    path=f"Postprocessors/{_ENERGY_INVENTORY_PP}",
                    type_name="ADElementIntegralFunctorPostprocessor",
                    parameters=(
                        ("functor", _ENERGY_DENSITY_J_FUNCTOR),
                        ("block", "plasma"),
                        ("execute_on", "'INITIAL TIMESTEP_END'"),
                    ),
                )
            )
        elif observation == "energy_profile":
            blocks.extend(
                (
                    MooseBlock(
                        path=f"Postprocessors/{_ENERGY_NORM_AVG_PP}",
                        type_name="ElementAverageFunctorPostprocessor",
                        parameters=(
                            ("functor", _ENERGY_VARIABLE),
                            ("block", "plasma"),
                            ("execute_on", "'INITIAL TIMESTEP_END'"),
                        ),
                    ),
                    MooseBlock(
                        path=f"Postprocessors/{_ENERGY_NORM_MIN_PP}",
                        type_name="ADElementExtremeFunctorValue",
                        parameters=(
                            ("functor", _ENERGY_VARIABLE),
                            ("value_type", "min"),
                            ("block", "plasma"),
                            ("execute_on", "'INITIAL TIMESTEP_END'"),
                        ),
                    ),
                    MooseBlock(
                        path=f"Postprocessors/{_ENERGY_NORM_MAX_PP}",
                        type_name="ADElementExtremeFunctorValue",
                        parameters=(
                            ("functor", _ENERGY_VARIABLE),
                            ("value_type", "max"),
                            ("block", "plasma"),
                            ("execute_on", "'INITIAL TIMESTEP_END'"),
                        ),
                    ),
                    MooseBlock(
                        path=f"Postprocessors/{_MEAN_EN_AVG_PP}",
                        type_name="ElementAverageFunctorPostprocessor",
                        parameters=(
                            ("functor", _MEAN_EN_SOLVED_FUNCTOR),
                            ("block", "plasma"),
                            ("execute_on", "'INITIAL TIMESTEP_END'"),
                        ),
                    ),
                    MooseBlock(
                        path=f"Postprocessors/{_MEAN_EN_MIN_PP}",
                        type_name="ADElementExtremeFunctorValue",
                        parameters=(
                            ("functor", _MEAN_EN_SOLVED_FUNCTOR),
                            ("value_type", "min"),
                            ("block", "plasma"),
                            ("execute_on", "'INITIAL TIMESTEP_END'"),
                        ),
                    ),
                    MooseBlock(
                        path=f"Postprocessors/{_MEAN_EN_MAX_PP}",
                        type_name="ADElementExtremeFunctorValue",
                        parameters=(
                            ("functor", _MEAN_EN_SOLVED_FUNCTOR),
                            ("value_type", "max"),
                            ("block", "plasma"),
                            ("execute_on", "'INITIAL TIMESTEP_END'"),
                        ),
                    ),
                )
            )
        else:
            raise MooseLoweringError(
                f"no MOOSE observation realization for {observation!r}"
            )
    unique: dict[str, MooseBlock] = {block.path: block for block in blocks}
    return tuple(unique[path] for path in sorted(unique))


def _lower_electron_energy_diffusion(
    case: ExecutionCase,
    model: str | None,
    execution_bounds: tuple[tuple[str, Any], ...],
) -> MooseCaseIR:
    raw_diffusivity = _parameter(case, "diffusivity")
    try:
        diffusivity = float(raw_diffusivity)
    except (TypeError, ValueError) as exc:
        raise MooseLoweringError("diffusivity must be numeric") from exc
    if not math.isfinite(diffusivity) or diffusivity < 0.0:
        raise MooseLoweringError("diffusivity must be finite and non-negative")

    blocks = (
        MooseBlock(
            path=f"Variables/{_ENERGY_VARIABLE}",
            type_name="MooseVariableFVReal",
            parameters=(("block", "plasma"),),
        ),
        MooseBlock(
            path=f"Functions/{_ENERGY_PROFILE_FUNCTION}",
            type_name="ParsedFunction",
            parameters=(("expression", f"'{_LOCALIZED_BUMP_EXPRESSION}'"),),
        ),
        MooseBlock(
            path=f"ICs/{_ENERGY_PROFILE_IC}",
            type_name="FunctionIC",
            parameters=(
                ("variable", _ENERGY_VARIABLE),
                ("function", _ENERGY_PROFILE_FUNCTION),
            ),
        ),
        *_energy_bridge_blocks(),
        MooseBlock(
            path=f"FunctorMaterials/{_ENERGY_DIFFUSIVITY_MATERIAL}",
            type_name="ADGenericFunctorMaterial",
            parameters=(
                ("prop_names", "'electron_energy_diffusivity_control'"),
                ("prop_values", f"'{diffusivity:.17g}'"),
                ("block", "plasma"),
            ),
        ),
        MooseBlock(
            path=f"FVKernels/{_ENERGY_TIME_KERNEL}",
            type_name="FVTimeKernel",
            parameters=(
                ("variable", _ENERGY_VARIABLE),
                ("block", "plasma"),
            ),
        ),
        MooseBlock(
            path=f"FVKernels/{_ENERGY_DIFFUSION_KERNEL}",
            type_name="FVDiffusion",
            parameters=(
                ("variable", _ENERGY_VARIABLE),
                ("coeff", "electron_energy_diffusivity_control"),
                ("block", "plasma"),
            ),
        ),
        *_observation_blocks(case.required_observations),
    )
    return MooseCaseIR(
        case_id=case.case_id,
        action_id=case.action_id,
        model=model,
        blocks=tuple(blocks),
        assignments=_execution_assignments(execution_bounds),
        required_observations=case.required_observations,
    )


def _lower_quasi_neutral_initialization(
    case: ExecutionCase,
    model: str | None,
    execution_bounds: tuple[tuple[str, Any], ...],
) -> MooseCaseIR:
    value = float(_parameter(case, "electron_reference_density_m3"))
    if not math.isfinite(value) or value <= 0.0:
        raise MooseLoweringError("electron reference density must be finite and positive")
    return MooseCaseIR(
        case_id=case.case_id,
        action_id=case.action_id,
        model=model,
        assignments=(
            MooseAssignment("", "n_e_value", f"{value:.17g}"),
            *_execution_assignments(execution_bounds),
        ),
        required_observations=case.required_observations,
    )


def _builtin_lowerer(case: ExecutionCase) -> BuiltinCaseLowerer:
    key = (case.target, case.intervention_type)
    if key in {
        ("electron_energy_transport", "PARAMETER_CONTROL"),
        ("electron_energy_transport", "PARAMETER_TREATMENT"),
    }:
        return _lower_electron_energy_diffusion
    if key == ("electron_reference_density", "DERIVED_INITIALIZATION"):
        return _lower_quasi_neutral_initialization
    raise MooseLoweringError(
        "no approved MOOSE realization for semantic action "
        f"target={case.target!r}, intervention_type={case.intervention_type!r}"
    )


def lower_execution_plan(
    plan: ExecutionPlan,
    *,
    lowerers: Mapping[str, CaseLowerer] | None = None,
) -> MooseTargetIR:
    """Lower an ExecutionPlan into structured target IR deterministically.

    Explicit ``lowerers`` are keyed by ActionSpec identity. Built-in dispatch is
    semantic (target + intervention type), never Issue-number based. Unsupported
    semantic actions fail explicitly rather than emitting placeholder MOOSE syntax.
    """
    lowerers = dict(lowerers or {})
    cases: list[MooseCaseIR] = []
    for case in plan.cases:
        explicit_lowerer = lowerers.get(case.action_id)
        if explicit_lowerer is not None:
            lowered = explicit_lowerer(case)
        else:
            lowered = _builtin_lowerer(case)(case, plan.model, plan.execution_bounds)
        if lowered.case_id != case.case_id or lowered.action_id != case.action_id:
            raise MooseLoweringError("target lowerer changed case/action identity")
        cases.append(lowered)
    return MooseTargetIR(
        source_plan_id=plan.plan_id,
        cases=tuple(cases),
        model=plan.model,
        execution_bounds=plan.execution_bounds,
    )


def _block_rank(path: str) -> tuple[int, str]:
    root = path.split("/", 1)[0]
    order = {
        "Variables": 10,
        "Functions": 20,
        "ICs": 30,
        "FunctorMaterials": 40,
        "FVKernels": 50,
        "Postprocessors": 60,
        "Executioner": 70,
    }
    return order.get(root, 100), path


def emit_moose_input(case: MooseCaseIR) -> str:
    """Emit deterministic MOOSE target text from structured IR."""
    lines: list[str] = [
        f"# QPX case_id: {case.case_id}",
        f"# QPX action_id: {case.action_id}",
    ]
    if case.model is not None:
        lines.append(f"# QPX model: {case.model}")

    top_level = sorted(
        (item for item in case.assignments if not item.path),
        key=lambda item: item.name,
    )
    for assignment in top_level:
        lines.append(f"{assignment.name} = {assignment.value}")

    assignments_by_path: dict[str, list[MooseAssignment]] = {}
    for assignment in case.assignments:
        if assignment.path:
            assignments_by_path.setdefault(assignment.path, []).append(assignment)

    block_map = {block.path: block for block in case.blocks}
    all_paths = sorted(
        set(block_map) | set(assignments_by_path),
        key=_block_rank,
    )
    for path in all_paths:
        block = block_map.get(path)
        lines.append(f"[{path}]")
        if block is not None and block.type_name is not None:
            lines.append(f"  type = {block.type_name}")
        parameters = list(block.parameters if block is not None else ())
        parameters.extend(
            (assignment.name, assignment.value)
            for assignment in assignments_by_path.get(path, ())
        )
        for name, value in sorted(parameters):
            lines.append(f"  {name} = {value}")
        lines.append("[]")

    for observation in sorted(case.required_observations):
        lines.append(f"# QPX observation: {observation}")
    return "\n".join(lines) + "\n"


__all__ = [
    "MooseAssignment", "MooseBlock", "MooseCaseIR", "MooseTargetIR",
    "MooseLoweringError", "lower_execution_plan", "emit_moose_input",
]
