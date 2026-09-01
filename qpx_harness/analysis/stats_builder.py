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
from .common import (
    build_problem_stats,
    build_environment_stats,
    build_common_stats,
    build_runtime_common_stats,
)
from .stats_builder_characterization import self_test


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


if __name__ == "__main__":
    raise SystemExit(self_test())
