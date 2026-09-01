"""Compatibility surface for the canonical performance investigation analyzer.

The implementation now lives in :mod:`qpx_harness.analysis.performance.investigation`.
Legacy imports remain valid during the compatibility-first package migration.
"""

from __future__ import annotations

from .analysis.performance import investigation as _investigation
from .analysis.performance.investigation import (
    CANONICAL_CLASSES,
    PerformanceContractError,
    build_investigation_summary,
    classify_bottleneck,
    discover_latest_smoke,
    main,
    perfgraph_nodes,
    petsc_events,
    run_investigation,
    self_test,
)

__all__ = [
    "CANONICAL_CLASSES",
    "PerformanceContractError",
    "build_investigation_summary",
    "classify_bottleneck",
    "discover_latest_smoke",
    "main",
    "perfgraph_nodes",
    "petsc_events",
    "run_investigation",
    "self_test",
]


def __getattr__(name: str):
    """Forward legacy private or incidental attribute access to the canonical module."""

    return getattr(_investigation, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_investigation)))


if __name__ == "__main__":
    raise SystemExit(main())
