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

from .metrics.efficiency import build_efficiency_stats
from .metrics.convergence import build_convergence_stats
from .metrics.accuracy import build_accuracy_stats


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


def build_runtime_simulation_stats(
    runtime: Mapping[str, Any],
    *,
    case_id: str | None = None,
    convergence: ConvergenceStats | None = None,
    accuracy: AccuracyStats | None = None,
) -> SimulationStats:
    """Construct SimulationStats from the shared issue-runtime fact shape."""

    return SimulationStats(
        common=build_runtime_common_stats(runtime, case_id=case_id),
        efficiency=None,
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