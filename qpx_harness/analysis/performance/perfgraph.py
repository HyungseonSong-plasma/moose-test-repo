"""Compatibility import for MOOSE PerfGraph decoding.

Raw MOOSE format ownership lives in ``qpx_harness.adapters.moose.performance``.
This facade is retained until #155 performance orchestration cleanup removes
legacy callers.
"""
from qpx_harness.adapters.moose.performance.perfgraph import (
    PerfGraphError,
    read_rows,
    rows_from_payload,
    self_test,
    sum_timer,
)

__all__ = ["PerfGraphError", "read_rows", "rows_from_payload", "self_test", "sum_timer"]

if __name__ == "__main__":
    raise SystemExit(self_test())
