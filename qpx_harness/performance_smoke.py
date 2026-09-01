"""Compatibility surface for the canonical performance smoke runner.

The implementation now lives in :mod:`qpx_harness.performance.smoke`.
Legacy imports remain valid during the compatibility-first package migration.
"""

from __future__ import annotations

from .performance import smoke as _smoke
from .performance.smoke import (
    PerformanceContractError,
    build_smoke_manifest,
    compare_smoke_results,
    create_run_root,
    default_results_root,
    main,
    run_smoke_pair,
    self_test,
)

__all__ = [
    "PerformanceContractError",
    "build_smoke_manifest",
    "compare_smoke_results",
    "create_run_root",
    "default_results_root",
    "main",
    "run_smoke_pair",
    "self_test",
]


def __getattr__(name: str):
    """Forward legacy private or incidental attribute access to the canonical module."""

    return getattr(_smoke, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_smoke)))


if __name__ == "__main__":
    raise SystemExit(main())
