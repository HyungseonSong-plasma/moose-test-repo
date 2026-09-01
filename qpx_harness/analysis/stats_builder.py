"""Build canonical Stats dataclasses from existing normalized QPX producer facts.

This module is the concrete model-construction boundary. Framework adapters and
existing producers keep their current normalized fact shapes; metrics,
diagnostics, ExecutionContract evaluation, and recipe policy remain outside.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from qpx_harness.models.stats import (
    AccuracyStats,
    CommonStats,
    ConvergenceStats,
    EfficiencyStats,
    EnvironmentStats,
    ErrorStats,
    InvariantErrorStats,
    MatrixBlockErrorStats,
    MatrixEntryErrorStats,
    MatrixErrorStats,
    MemoryStats,
    ProblemStats,
    ReferenceErrorStats,
    ResidualSample,
    ScalingFactorStats,
    SimulationStats,
    SolverConfigStats,
    SolverTerminationStats,
    TimingStats,
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def build_problem_stats(facts: Mapping[str, Any] | None) -> ProblemStats | None:
    """Map a normalized problem-identity mapping without adding interpretation."""

    if not facts:
        return None
    return ProblemStats(
        nodes=_optional_int(facts.get("nodes")),
        elements=_optional_int(facts.get("elements")),
        dofs=_optional_int(facts.get("dofs")),
        variables=_string_tuple(facts.get("variables")),
        species=_string_tuple(facts.get("species")),
    )


def build_environment_stats(
    facts: Mapping[str, Any] | None,
) -> EnvironmentStats | None:
    """Map environment/framework identity facts using existing producer names."""

    if not facts:
        return None
    return EnvironmentStats(
        hostname=facts.get("hostname") if isinstance(facts.get("hostname"), str) else None,
        platform=facts.get("platform") if isinstance(facts.get("platform"), str) else None,
        system=facts.get("system") if isinstance(facts.get("system"), str) else None,
        machine=facts.get("machine") if isinstance(facts.get("machine"), str) else None,
        processor=facts.get("processor") if isinstance(facts.get("processor"), str) else None,
        python_version=facts.get("python")
        if isinstance(facts.get("python"), str)
        else (
            facts.get("python_version")
            if isinstance(facts.get("python_version"), str)
            else None
        ),
        mpi_ranks=_optional_int(facts.get("mpi_ranks")),
        threads=_optional_int(facts.get("threads")),
        qpx_realpath=facts.get("qpx_realpath")
        if isinstance(facts.get("qpx_realpath"), str)
        else None,
        moose_version=facts.get("moose")
        if isinstance(facts.get("moose"), str)
        else (
            facts.get("moose_version")
            if isinstance(facts.get("moose_version"), str)
            else None
        ),
        libmesh_version=facts.get("libmesh")
        if isinstance(facts.get("libmesh"), str)
        else (
            facts.get("libmesh_version")
            if isinstance(facts.get("libmesh_version"), str)
            else None
        ),
        petsc_version=facts.get("petsc")
        if isinstance(facts.get("petsc"), str)
        else (
            facts.get("petsc_version")
            if isinstance(facts.get("petsc_version"), str)
            else None
        ),
        slepc_version=facts.get("slepc")
        if isinstance(facts.get("slepc"), str)
        else (
            facts.get("slepc_version")
            if isinstance(facts.get("slepc_version"), str)
            else None
        ),
        logical_cpu_count=_optional_int(facts.get("logical_cpu_count")),
    )


def _runtime_return_code(record: Mapping[str, Any]) -> int | None:
    direct = _optional_int(record.get("return_code"))
    if direct is not None:
        return direct
    validation = _mapping(record.get("validation"))
    p3 = _optional_int(validation.get("p3_returncode"))
    if p3 is not None:
        return p3
    return _optional_int(validation.get("p2_returncode"))


def build_common_stats(record: Mapping[str, Any]) -> CommonStats:
    """Build common run facts from an existing result-style producer record."""

    performance = _mapping(record.get("performance"))
    backend = record.get("backend") if isinstance(record.get("backend"), str) else None
    timestamp = (
        record.get("timestamp_iso")
        if isinstance(record.get("timestamp_iso"), str)
        else None
    )
    case_id = record.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("stats builder requires a non-empty case_id")
    return CommonStats(
        case_id=case_id,
        run_id=record.get("run_id") if isinstance(record.get("run_id"), str) else None,
        experiment_id=record.get("experiment_id")
        if isinstance(record.get("experiment_id"), str)
        else None,
        backend=backend,
        return_code=_runtime_return_code(record),
        wall_time_seconds=_optional_float(performance.get("wall_seconds")),
        timestamp_iso=timestamp,
        problem=build_problem_stats(_mapping(record.get("problem"))),
        environment=build_environment_stats(_mapping(record.get("environment"))),
    )


def build_runtime_common_stats(
    runtime: Mapping[str, Any],
    *,
    case_id: str | None = None,
) -> CommonStats:
    """Map the shared issue-runtime shape into CommonStats through one boundary."""

    resolved_case_id = case_id if case_id is not None else runtime.get("case_id")
    return build_common_stats(
        {
            "case_id": resolved_case_id,
            "return_code": runtime.get("returncode"),
            "performance": {"wall_seconds": runtime.get("wall_seconds")},
        }
    )


def _perfgraph_timings(perfgraph: Mapping[str, Any]) -> list[TimingStats]:
    rows: list[TimingStats] = []
    nodes = perfgraph.get("nodes")
    if not isinstance(nodes, list):
        return rows
    for node in nodes:
        if not isinstance(node, Mapping) or not isinstance(node.get("name"), str):
            continue
        rows.append(
            TimingStats(
                name=node["name"],
                source="moose_perfgraph",
                self_seconds=_optional_float(node.get("self_seconds")),
                call_count=_optional_int(
                    node.get("num_calls")
                    if node.get("num_calls") is not None
                    else node.get("call_count")
                ),
                parent=node.get("parent")
                if isinstance(node.get("parent"), str)
                else None,
                level=_optional_int(node.get("level")),
            )
        )
    return rows


def _petsc_timings(petsc: Mapping[str, Any]) -> list[TimingStats]:
    rows: list[TimingStats] = []
    events = petsc.get("rows")
    if not isinstance(events, list):
        return rows
    for event in events:
        if not isinstance(event, Mapping):
            continue
        name = event.get("Event Name")
        if not isinstance(name, str) or not name or name == "summary":
            continue
        rows.append(
            TimingStats(
                name=name,
                source="petsc_log",
                call_count=_optional_int(event.get("Count")),
                rank=_optional_int(event.get("Rank")),
                total_seconds=_optional_float(event.get("Time")),
            )
        )
    return rows


def _memory_stats(perfgraph: Mapping[str, Any]) -> list[MemoryStats]:
    rows: list[MemoryStats] = []
    this_rank = _optional_float(perfgraph.get("max_memory_this_rank_mb"))
    if this_rank is not None:
        rows.append(
            MemoryStats(
                kind="max_memory_this_rank",
                value=this_rank,
                unit="MB",
                source="moose_perfgraph",
            )
        )
    per_rank = perfgraph.get("max_memory_per_rank_mb")
    if isinstance(per_rank, list):
        for rank, value in enumerate(per_rank):
            number = _optional_float(value)
            if number is not None:
                rows.append(
                    MemoryStats(
                        kind="max_memory_per_rank",
                        value=number,
                        unit="MB",
                        source="moose_perfgraph",
                        rank=rank,
                    )
                )
    return rows


def build_efficiency_stats(record: Mapping[str, Any]) -> EfficiencyStats | None:
    """Build work/timing/resource facts from a performance-style result record."""

    work = _mapping(record.get("work"))
    performance = _mapping(record.get("performance"))
    perfgraph = _mapping(performance.get("perfgraph"))
    petsc = _mapping(performance.get("petsc"))
    timings = (*_perfgraph_timings(perfgraph), *_petsc_timings(petsc))
    memories = tuple(_memory_stats(perfgraph))
    peak_rss_bytes = _optional_int(performance.get("peak_rss_bytes"))
    residual_evaluations = _optional_int(work.get("residual_evaluations"))
    jacobian_evaluations = _optional_int(work.get("jacobian_evaluations"))
    if (
        peak_rss_bytes is None
        and residual_evaluations is None
        and jacobian_evaluations is None
        and not timings
        and not memories
    ):
        return None
    return EfficiencyStats(
        peak_rss_bytes=peak_rss_bytes,
        residual_evaluations=residual_evaluations,
        jacobian_evaluations=jacobian_evaluations,
        timings=tuple(timings),
        memories=memories,
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
                iteration_count=_optional_int(
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
        iteration = _optional_int(row.get("iteration"))
        for key, kind in keys:
            value = _optional_float(row.get(key))
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
            value = _optional_float(raw)
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
            value = _optional_float(raw)
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

    work_map = _mapping(work)
    ksp = _mapping(ksp_view)
    trajectory_map = _mapping(trajectory)
    solver = None
    if ksp:
        solver = SolverConfigStats(
            linear_solver=ksp.get("ksp_type")
            if isinstance(ksp.get("ksp_type"), str)
            else None,
            preconditioner=ksp.get("pc_type")
            if isinstance(ksp.get("pc_type"), str)
            else None,
            linear_restart=_optional_int(ksp.get("restart")),
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
    linear_iterations = _optional_int(work_map.get("linear_iterations"))
    nonlinear_iterations = _optional_int(work_map.get("nonlinear_iterations"))
    physical_step_count = _optional_int(
        trajectory_map.get("physical_rows")
        if trajectory_map.get("physical_rows") is not None
        else trajectory_map.get("physical_step_count")
    )
    first_time = _optional_float(
        trajectory_map.get("first_time")
        if trajectory_map.get("first_time") is not None
        else trajectory_map.get("first_time_seconds")
    )
    final_time = _optional_float(
        trajectory_map.get("final_time")
        if trajectory_map.get("final_time") is not None
        else trajectory_map.get("final_time_seconds")
    )
    dt_min = _optional_float(
        trajectory_map.get("actual_dt_min")
        if trajectory_map.get("actual_dt_min") is not None
        else trajectory_map.get("actual_dt_min_seconds")
    )
    dt_max = _optional_float(
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


def _error_from_mapping(
    row: Mapping[str, Any],
    *,
    relative_keys: tuple[str, ...] = ("relative_error",),
    absolute_keys: tuple[str, ...] = ("absolute_error",),
    norm_type: str | None = None,
    reference_id: str | None = None,
) -> ErrorStats:
    relative = next(
        (
            value
            for key in relative_keys
            if (value := _optional_float(row.get(key))) is not None
        ),
        None,
    )
    absolute = next(
        (
            value
            for key in absolute_keys
            if (value := _optional_float(row.get(key))) is not None
        ),
        None,
    )
    return ErrorStats(
        absolute_error=absolute,
        relative_error=relative,
        norm_type=norm_type,
        reference_id=reference_id,
    )


def _matrix_blocks(value: Any) -> tuple[MatrixBlockErrorStats, ...]:
    if isinstance(value, Mapping):
        rows = value.values()
    elif isinstance(value, list):
        rows = value
    else:
        return ()
    out: list[MatrixBlockErrorStats] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        row_var = row.get("row_variable")
        col_var = row.get("col_variable")
        count = _optional_int(
            row.get("count")
            if row.get("count") is not None
            else row.get("entry_count")
        )
        if not isinstance(row_var, str) or not isinstance(col_var, str) or count is None:
            continue
        out.append(
            MatrixBlockErrorStats(
                row_variable=row_var,
                col_variable=col_var,
                entry_count=count,
                l2_difference=_optional_float(row.get("l2_difference")),
                max_abs_difference=_optional_float(row.get("max_abs_difference")),
                energy_fraction=_optional_float(row.get("energy_fraction")),
                sum_squared_difference=_optional_float(
                    row.get("sum_squared_difference")
                ),
            )
        )
    return tuple(out)


def _matrix_entries(value: Any) -> tuple[MatrixEntryErrorStats, ...]:
    if not isinstance(value, list):
        return ()
    out: list[MatrixEntryErrorStats] = []
    for row in value:
        if not isinstance(row, Mapping):
            continue
        r = _optional_int(row.get("row"))
        c = _optional_int(row.get("col"))
        difference = _optional_float(
            row.get("value")
            if row.get("value") is not None
            else row.get("difference")
        )
        if r is None or c is None or difference is None:
            continue
        out.append(
            MatrixEntryErrorStats(
                row=r,
                col=c,
                difference=difference,
                row_variable=row.get("row_variable")
                if isinstance(row.get("row_variable"), str)
                else None,
                col_variable=row.get("col_variable")
                if isinstance(row.get("col_variable"), str)
                else None,
            )
        )
    return tuple(out)


def build_accuracy_stats(
    *,
    jacobian_comparisons: Iterable[Mapping[str, Any]] = (),
    reference_comparisons: Iterable[Mapping[str, Any]] = (),
    invariants: Iterable[Mapping[str, Any]] = (),
    matrix_comparisons: Iterable[Mapping[str, Any]] = (),
) -> AccuracyStats | None:
    """Map existing reference/invariant/Jacobian facts without acceptance policy."""

    matrix_errors: list[MatrixErrorStats] = []
    for index, row in enumerate(jacobian_comparisons):
        if not isinstance(row, Mapping):
            continue
        matrix_errors.append(
            MatrixErrorStats(
                name="jacobian_fd",
                error=_error_from_mapping(
                    row,
                    relative_keys=("relative_frobenius_error",),
                    absolute_keys=("absolute_frobenius_error",),
                    norm_type="Frobenius",
                    reference_id="finite_difference_jacobian",
                ),
                comparison_index=index,
            )
        )

    reference_errors: list[ReferenceErrorStats] = []
    for row in reference_comparisons:
        if not isinstance(row, Mapping):
            continue
        name = row.get("name") if isinstance(row.get("name"), str) else row.get("key")
        if not isinstance(name, str):
            continue
        observed = _optional_float(
            row.get("observed_value")
            if row.get("observed_value") is not None
            else row.get("candidate")
        )
        reference = _optional_float(
            row.get("reference_value")
            if row.get("reference_value") is not None
            else row.get("legacy")
        )
        reference_errors.append(
            ReferenceErrorStats(
                name=name,
                error=_error_from_mapping(
                    row,
                    reference_id=row.get("reference_id")
                    if isinstance(row.get("reference_id"), str)
                    else None,
                ),
                observed_value=observed,
                reference_value=reference,
            )
        )

    invariant_errors: list[InvariantErrorStats] = []
    for row in invariants:
        if not isinstance(row, Mapping) or not isinstance(row.get("name"), str):
            continue
        invariant_errors.append(
            InvariantErrorStats(
                name=row["name"],
                error=_error_from_mapping(
                    row,
                    reference_id=row.get("reference_id")
                    if isinstance(row.get("reference_id"), str)
                    else None,
                ),
                observed_value=_optional_float(row.get("observed_value")),
                reference_value=_optional_float(row.get("reference_value")),
            )
        )

    for index, row in enumerate(matrix_comparisons):
        if not isinstance(row, Mapping):
            continue
        name = row.get("name") if isinstance(row.get("name"), str) else "matrix_difference"
        matrix_errors.append(
            MatrixErrorStats(
                name=name,
                error=_error_from_mapping(
                    row,
                    relative_keys=("relative_error", "relative_frobenius_error"),
                    absolute_keys=("absolute_error", "absolute_frobenius_error"),
                    norm_type=row.get("norm_type")
                    if isinstance(row.get("norm_type"), str)
                    else None,
                    reference_id=row.get("reference_id")
                    if isinstance(row.get("reference_id"), str)
                    else None,
                ),
                threshold=_optional_float(row.get("threshold")),
                structural_entry_count=_optional_int(row.get("structural_entry_count")),
                nonzero_thresholded_entry_count=_optional_int(
                    row.get("nonzero_thresholded_entry_count")
                ),
                thresholded_l2_difference=_optional_float(
                    row.get("thresholded_l2_difference")
                ),
                blocks=_matrix_blocks(row.get("blocks")),
                comparison_index=_optional_int(row.get("comparison_index"))
                if row.get("comparison_index") is not None
                else index,
                entries=_matrix_entries(row.get("entries")),
                section_observed=row.get("section_observed")
                if isinstance(row.get("section_observed"), bool)
                else None,
                mapped_entry_count=_optional_int(row.get("mapped_entry_count")),
            )
        )

    if not matrix_errors and not reference_errors and not invariant_errors:
        return None
    return AccuracyStats(
        invariant_errors=tuple(invariant_errors),
        matrix_errors=tuple(matrix_errors),
        reference_errors=tuple(reference_errors),
    )


def build_simulation_stats(
    performance_record: Mapping[str, Any],
    *,
    convergence: ConvergenceStats | None = None,
    accuracy: AccuracyStats | None = None,
) -> SimulationStats:
    """Construct one SimulationStats while keeping policy and evidence separate."""

    return SimulationStats(
        common=build_common_stats(performance_record),
        efficiency=build_efficiency_stats(performance_record),
        convergence=convergence,
        accuracy=accuracy,
    )


def self_test() -> int:
    """P0 characterization of representative existing producer fact shapes."""

    try:
        performance = {
            "run_id": "run-1",
            "experiment_id": "exp-1",
            "case_id": "case-1",
            "environment": {
                "hostname": "host",
                "platform": "linux",
                "python": "3.12",
                "mpi_ranks": 2,
                "threads": 4,
                "logical_cpu_count": 16,
                "qpx_realpath": "/opt/qpx-opt",
                "moose": "moose-v",
                "petsc": "petsc-v",
            },
            "problem": {
                "nodes": 10,
                "elements": 8,
                "dofs": 12,
                "variables": ["u", "v"],
                "species": ["O2", "O"],
            },
            "work": {
                "nonlinear_iterations": 3,
                "linear_iterations": 9,
                "residual_evaluations": 5,
                "jacobian_evaluations": 2,
            },
            "performance": {
                "wall_seconds": 1.25,
                "max_memory_mb": 128.0,
                "perfgraph": {
                    "max_memory_this_rank_mb": 128.0,
                    "max_memory_per_rank_mb": [128.0, 96.0],
                    "nodes": [
                        {
                            "name": "app",
                            "parent": None,
                            "level": 0,
                            "self_seconds": 0.25,
                            "num_calls": 1,
                        }
                    ],
                },
                "petsc": {
                    "rows": [
                        {
                            "Event Name": "SNESJacobianEval",
                            "Rank": 0,
                            "Count": 2,
                            "Time": 0.4,
                        }
                    ]
                },
            },
            "validation": {
                "status": "P2_PASS_P3_PASS",
                "p2_returncode": 0,
                "p3_returncode": 0,
            },
            "execution_contract": {"decision": "must remain outside Stats"},
            "scientific_decision": "must remain outside Stats",
        }
        convergence = build_convergence_stats(
            work=performance["work"],
            linear_terminations=[
                {
                    "converged": False,
                    "reason": "DIVERGED_BREAKDOWN",
                    "iterations": 30,
                }
            ],
            nonlinear_terminations=[
                {
                    "converged": True,
                    "reason": "CONVERGED_FNORM_ABS",
                    "iterations": 2,
                }
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
        accuracy = build_accuracy_stats(
            jacobian_comparisons=[
                {
                    "relative_frobenius_error": 5.0e-11,
                    "absolute_frobenius_error": 1.0e-8,
                }
            ],
            reference_comparisons=[
                {
                    "key": "Dmix_A_O2",
                    "candidate": 1.01,
                    "legacy": 1.00,
                    "relative_error": 0.01,
                }
            ],
            invariants=[
                {
                    "name": "electron_inventory",
                    "observed_value": 10.0,
                    "reference_value": 10.0,
                    "relative_error": 0.0,
                }
            ],
            matrix_comparisons=[
                {
                    "name": "thresholded_jacobian_difference",
                    "threshold": 1.0e-6,
                    "section_observed": True,
                    "structural_entry_count": 2,
                    "nonzero_thresholded_entry_count": 1,
                    "mapped_entry_count": 1,
                    "thresholded_l2_difference": 0.25,
                    "entries": [
                        {
                            "row": 1,
                            "col": 2,
                            "value": 0.25,
                            "row_variable": "u",
                            "col_variable": "v",
                        }
                    ],
                    "blocks": {
                        "u->v": {
                            "row_variable": "u",
                            "col_variable": "v",
                            "count": 1,
                            "sum_squared_difference": 0.0625,
                            "max_abs_difference": 0.25,
                            "l2_difference": 0.25,
                        }
                    },
                }
            ],
        )
        stats = build_simulation_stats(
            performance,
            convergence=convergence,
            accuracy=accuracy,
        )

        assert stats.common.case_id == "case-1"
        assert stats.common.wall_time_seconds == 1.25
        assert stats.common.environment is not None
        assert stats.common.environment.logical_cpu_count == 16
        assert stats.efficiency is not None
        assert stats.efficiency.jacobian_evaluations == 2
        assert any(t.source == "petsc_log" and t.total_seconds == 0.4 for t in stats.efficiency.timings)
        assert len(stats.efficiency.memories) == 3
        assert stats.convergence is not None
        assert stats.convergence.terminations[0].converged is False
        assert stats.convergence.solver is not None
        assert stats.convergence.solver.linear_restart == 30
        assert len(stats.convergence.residuals) == 5
        assert len(stats.convergence.scaling_factors) == 2
        assert stats.accuracy is not None
        assert stats.accuracy.matrix_errors[0].error.relative_error == 5.0e-11
        assert stats.accuracy.reference_errors[0].observed_value == 1.01
        thresholded = stats.accuracy.matrix_errors[1]
        assert thresholded.blocks[0].sum_squared_difference == 0.0625
        assert thresholded.entries[0].difference == 0.25

        assert not hasattr(stats, "execution_contract")
        assert not hasattr(stats, "scientific_decision")

        try:
            build_common_stats({"run_id": "missing-case"})
        except ValueError:
            pass
        else:
            raise AssertionError("missing case_id was accepted")
    except Exception as exc:
        print(f"QPX_STATS_BUILDER_SELFTEST: FAIL ({exc})")
        return 1

    print("QPX_STATS_BUILDER_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
