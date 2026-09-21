"""Build canonical Stats dataclasses from existing normalized QPX producer facts.

This module is the concrete model-construction boundary. Framework adapters and
existing producers keep their current normalized fact shapes; metrics,
diagnostics, ExecutionContract evaluation, and recipe policy remain outside.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from physics_harness.evaluation.statistics import AccuracyStats, ConvergenceStats, SimulationStats

from .metrics.efficiency import build_efficiency_stats
from .metrics.convergence import build_convergence_stats
from .metrics.accuracy import build_accuracy_stats
from .common import (
    build_problem_stats,
    build_environment_stats,
    build_common_stats,
    build_runtime_common_stats,
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


__all__ = [
    "build_accuracy_stats",
    "build_common_stats",
    "build_convergence_stats",
    "build_efficiency_stats",
    "build_environment_stats",
    "build_problem_stats",
    "build_runtime_common_stats",
    "build_runtime_simulation_stats",
    "build_simulation_stats",
]
