"""Compatibility surface for the canonical direct transport probe backend.

The implementation now lives in :mod:`qpx_harness.performance.probes.transport`.
Legacy imports remain valid during the compatibility-first package migration.
"""

from __future__ import annotations

from .performance.probes import transport as _transport
from .performance.probes.transport import (
    MARKER_PREFIX,
    PROBE_MACRO,
    TIMER_NAMES,
    ProbeError,
    analyze_probe,
    instrument_source,
    main,
    self_test,
)

__all__ = [
    "MARKER_PREFIX",
    "PROBE_MACRO",
    "TIMER_NAMES",
    "ProbeError",
    "analyze_probe",
    "instrument_source",
    "main",
    "self_test",
]


def __getattr__(name: str):
    """Forward legacy private or incidental attribute access to the canonical backend."""

    return getattr(_transport, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_transport)))


if __name__ == "__main__":
    raise SystemExit(main())
