"""ConvergenceStats mapping from normalized solver and trajectory facts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .._coerce import as_mapping, optional_float, optional_int
from ...evaluation.statistics import (
    ConvergenceStats,
    ResidualSample,
    ScalingFactorStats,
    SolverConfigStats,
    SolverTerminationStats,
)


def _termination_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    solver: str,
) -> list[SolverTerminationStats]:
    out: list[SolverTerminationStats] = []
    for index, row in enumerate(rows):
        reason = row.get("reason")
        if not isinstance(reason, str):
            continue
        converged = row.get("converged")
        out.append(
            SolverTerminationStats(
                solver=solver,
                reason=reason,
                solve_index=index,
                iteration_count=optional_int(
                    row.get("iterations")
                    if row.get("iterations") is not None
                    else row.get("iteration_count")
                ),
                converged=converged if isinstance(converged, bool) else None,
            )
        )
    return out


def _true_residual_samples(
    rows: Iterable[Mapping[str, Any]],
) -> list[ResidualSample]:
    out: list[ResidualSample] = []
    keys = (
        ("reported_residual", "petsc_reported"),
        ("true_residual", "petsc_true"),
        ("relative_true_residual", "petsc_relative_true"),
    )
    for row in rows:
        iteration = optional_int(row.get("iteration"))
        for key, kind in keys:
            value = optional_float(row.get(key))
            if value is not None:
                out.append(
                    ResidualSample(
                        value=value,
                        kind=kind,
                        iteration=iteration,
                    )
                )
    return out


def _variable_residual_samples(
    blocks: Iterable[Mapping[str, Any]],
) -> list[ResidualSample]:
    out: list[ResidualSample] = []
    for block_index, block in enumerate(blocks):
        for variable, raw in block.items():
            if not isinstance(variable, str):
                continue
            value = optional_float(raw)
            if value is None:
                continue
            out.append(
                ResidualSample(
                    value=value,
                    kind="moose_variable_l2",
                    solve_index=block_index,
                    variable=variable,
                    norm_type="L2",
                )
            )
    return out


def _scaling_factor_rows(
    blocks: Iterable[Mapping[str, Any]],
) -> list[ScalingFactorStats]:
    out: list[ScalingFactorStats] = []
    for block_index, block in enumerate(blocks):
        for variable, raw in block.items():
            if not isinstance(variable, str):
                continue
            value = optional_float(raw)
            if value is not None:
                out.append(
                    ScalingFactorStats(
                        variable=variable,
                        value=value,
                        block_index=block_index,
                    )
                )
    return out


def build_convergence_stats(
    *,
    work: Mapping[str, Any] | None = None,
    linear_terminations: Iterable[Mapping[str, Any]] = (),
    nonlinear_terminations: Iterable[Mapping[str, Any]] = (),
    ksp_view: Mapping[str, Any] | None = None,
    true_residuals: Iterable[Mapping[str, Any]] = (),
    variable_residual_blocks: Iterable[Mapping[str, Any]] = (),
    scaling_factor_blocks: Iterable[Mapping[str, Any]] = (),
    trajectory: Mapping[str, Any] | None = None,
) -> ConvergenceStats | None:
    """Map already-parsed solver and trajectory facts into convergence Stats."""

    work_map = as_mapping(work)
    ksp = as_mapping(ksp_view)
    trajectory_map = as_mapping(trajectory)
    solver = None
    if ksp:
        solver = SolverConfigStats(
            linear_solver=ksp.get("ksp_type")
            if isinstance(ksp.get("ksp_type"), str)
            else None,
            preconditioner=ksp.get("pc_type")
            if isinstance(ksp.get("pc_type"), str)
            else None,
            linear_restart=optional_int(ksp.get("restart")),
        )
    terminations = (
        *_termination_rows(linear_terminations, solver="linear"),
        *_termination_rows(nonlinear_terminations, solver="nonlinear"),
    )
    residuals = (
        *_true_residual_samples(true_residuals),
        *_variable_residual_samples(variable_residual_blocks),
    )
    scaling_factors = tuple(_scaling_factor_rows(scaling_factor_blocks))
    linear_iterations = optional_int(work_map.get("linear_iterations"))
    nonlinear_iterations = optional_int(work_map.get("nonlinear_iterations"))
    physical_step_count = optional_int(
        trajectory_map.get("physical_rows")
        if trajectory_map.get("physical_rows") is not None
        else trajectory_map.get("physical_step_count")
    )
    first_time = optional_float(
        trajectory_map.get("first_time")
        if trajectory_map.get("first_time") is not None
        else trajectory_map.get("first_time_seconds")
    )
    final_time = optional_float(
        trajectory_map.get("final_time")
        if trajectory_map.get("final_time") is not None
        else trajectory_map.get("final_time_seconds")
    )
    dt_min = optional_float(
        trajectory_map.get("actual_dt_min")
        if trajectory_map.get("actual_dt_min") is not None
        else trajectory_map.get("actual_dt_min_seconds")
    )
    dt_max = optional_float(
        trajectory_map.get("actual_dt_max")
        if trajectory_map.get("actual_dt_max") is not None
        else trajectory_map.get("actual_dt_max_seconds")
    )
    if (
        linear_iterations is None
        and nonlinear_iterations is None
        and physical_step_count is None
        and first_time is None
        and final_time is None
        and dt_min is None
        and dt_max is None
        and solver is None
        and not terminations
        and not residuals
        and not scaling_factors
    ):
        return None
    return ConvergenceStats(
        linear_iterations=linear_iterations,
        nonlinear_iterations=nonlinear_iterations,
        physical_step_count=physical_step_count,
        first_time_seconds=first_time,
        final_time_seconds=final_time,
        actual_dt_min_seconds=dt_min,
        actual_dt_max_seconds=dt_max,
        solver=solver,
        terminations=tuple(terminations),
        residuals=tuple(residuals),
        scaling_factors=scaling_factors,
    )


def self_test() -> int:
    try:
        stats = build_convergence_stats(
            work={"linear_iterations": 9, "nonlinear_iterations": 3},
            linear_terminations=[
                {"converged": False, "reason": "DIVERGED_BREAKDOWN", "iterations": 30}
            ],
            nonlinear_terminations=[
                {"converged": True, "reason": "CONVERGED_FNORM_ABS", "iterations": 2}
            ],
            ksp_view={"ksp_type": "gmres", "restart": 30, "pc_type": "lu"},
            true_residuals=[
                {
                    "iteration": 0,
                    "reported_residual": 1.0,
                    "true_residual": 0.8,
                    "relative_true_residual": 0.4,
                }
            ],
            variable_residual_blocks=[{"u": 1.0e-4, "v": 2.0e-4}],
            scaling_factor_blocks=[{"u": 2.0, "v": 4.0}],
            trajectory={
                "physical_rows": 5,
                "first_time": 1.0e-13,
                "final_time": 5.0e-13,
                "actual_dt_min": 1.0e-13,
                "actual_dt_max": 1.0e-13,
            },
        )
        if stats is None:
            raise AssertionError("representative convergence facts produced None")
        if (
            stats.linear_iterations != 9
            or stats.nonlinear_iterations != 3
            or stats.physical_step_count != 5
            or stats.solver is None
            or stats.solver.linear_solver != "gmres"
            or stats.solver.preconditioner != "lu"
            or stats.solver.linear_restart != 30
            or len(stats.terminations) != 2
            or len(stats.residuals) != 5
            or len(stats.scaling_factors) != 2
        ):
            raise AssertionError("ConvergenceStats mapping drifted")
        if stats.terminations[0].converged is not False:
            raise AssertionError("linear termination semantics drifted")
        if build_convergence_stats() is not None:
            raise AssertionError("empty facts invented ConvergenceStats")
    except Exception as exc:
        print(f"QPX_CONVERGENCE_STATS_MAPPING_SELFTEST: FAIL ({exc})")
        return 1

    print("QPX_CONVERGENCE_STATS_MAPPING_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
