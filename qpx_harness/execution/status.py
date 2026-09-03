"""Canonical presentation-neutral mechanical state classification for QPX execution.

Execution state describes process/liveness mechanics only. Scientific acceptance,
validation policy, and diagnosis outcomes belong to their owning layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .runtime import TelemetrySample


class ExecutionState(str, Enum):
    """Mechanical execution/liveness states; never scientific PASS/FAIL."""

    CALCULATING = "CALCULATING"
    WAITING = "WAITING"
    STALL_SUSPECTED = "STALL_SUSPECTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass
class LivenessClassifier:
    """Classify raw runtime telemetry without deciding how states are displayed."""

    stall_after_seconds: float = 60.0
    cpu_progress_seconds: float = 0.02
    _previous_cpu_seconds: float | None = 0.0
    _previous_log_size: int = 0
    _last_activity_elapsed: float = 0.0

    def classify(self, sample: TelemetrySample) -> ExecutionState:
        cpu_observable = (
            sample.cpu_seconds is not None and self._previous_cpu_seconds is not None
        )
        cpu_progress = (
            cpu_observable
            and sample.cpu_seconds is not None
            and self._previous_cpu_seconds is not None
            and sample.cpu_seconds - self._previous_cpu_seconds
            >= self.cpu_progress_seconds
        )
        output_progress = sample.log_size > self._previous_log_size

        if cpu_progress or output_progress:
            self._last_activity_elapsed = sample.elapsed_seconds
            state = ExecutionState.CALCULATING
        elif not cpu_observable:
            state = ExecutionState.CALCULATING
        elif sample.elapsed_seconds - self._last_activity_elapsed >= self.stall_after_seconds:
            state = ExecutionState.STALL_SUSPECTED
        else:
            state = ExecutionState.WAITING

        self._previous_cpu_seconds = sample.cpu_seconds
        self._previous_log_size = sample.log_size
        return state
