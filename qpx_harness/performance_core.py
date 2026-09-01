"""Compatibility surface for the canonical performance runner.

The implementation now lives in :mod:`qpx_harness.performance.runner`.
Legacy imports remain valid during the compatibility-first package migration.
"""

from __future__ import annotations

from .performance import runner as _runner
from .performance.runner import (
    RESULT_STATUSES,
    SCHEMA_VERSION,
    VALID_MODES,
    PerformanceContractError,
    collect_environment,
    collect_perfgraph_json,
    collect_petsc_csv,
    main,
    parse_framework_identity,
    parse_problem_identity,
    read_last_metrics_row,
    run_measurement,
    self_test,
    validate_experiment_manifest,
    validate_result_record,
    write_measurement_overlay,
)

__all__ = [
    "RESULT_STATUSES",
    "SCHEMA_VERSION",
    "VALID_MODES",
    "PerformanceContractError",
    "collect_environment",
    "collect_perfgraph_json",
    "collect_petsc_csv",
    "main",
    "parse_framework_identity",
    "parse_problem_identity",
    "read_last_metrics_row",
    "run_measurement",
    "self_test",
    "validate_experiment_manifest",
    "validate_result_record",
    "write_measurement_overlay",
]


def __getattr__(name: str):
    """Forward legacy private attribute access to the canonical runner."""

    return getattr(_runner, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_runner)))


if __name__ == "__main__":
    raise SystemExit(main())
