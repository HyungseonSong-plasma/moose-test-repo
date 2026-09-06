"""Deprecated compatibility surface for MOOSE PerfGraph helpers.

Raw MOOSE PerfGraph decoding is owned by
``qpx_harness.adapters.moose.performance.perfgraph``. This forwarding module
exists only so characterization/study consumers can migrate independently; it
contains no external-format parser or MOOSE syntax knowledge and is targeted
for retirement with the WB5 performance orchestration cleanup.
"""
from qpx_harness.adapters.moose.performance.perfgraph import (
    PerfGraphError,
    read_rows,
    rows_from_payload,
    self_test,
    sum_timer,
)

__all__ = ["PerfGraphError", "read_rows", "rows_from_payload", "self_test", "sum_timer"]
