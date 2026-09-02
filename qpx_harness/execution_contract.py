"""Compatibility facade for the canonical execution-contract capability.

The implementation owner is :mod:`qpx_harness.execution.contract`. New code
should import that module directly. This facade temporarily preserves the
historical import path and direct-script CLI while consumers migrate.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Preserve ``python qpx_harness/execution_contract.py ...`` from a repository
# checkout: direct script execution otherwise places qpx_harness/, not its
# parent repository directory, at sys.path[0].
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qpx_harness.execution.contract import (  # noqa: E402
    DECISIONS,
    OPERATORS,
    OPS,
    PHASES,
    SCHEMA_VERSION,
    SEVERITIES,
    CheckOperand,
    ExecutionContractError,
    evaluate_contract,
    main,
    self_test,
    validate_contract,
)

__all__ = [
    "DECISIONS",
    "OPERATORS",
    "OPS",
    "PHASES",
    "SCHEMA_VERSION",
    "SEVERITIES",
    "CheckOperand",
    "ExecutionContractError",
    "evaluate_contract",
    "main",
    "self_test",
    "validate_contract",
]


if __name__ == "__main__":
    raise SystemExit(main())
