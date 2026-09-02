"""Compatibility surface for the canonical managed probe runtime.

The implementation now lives in :mod:`qpx_harness.performance.probes.runtime`.
Legacy imports remain valid during the compatibility-first package migration.
"""

from __future__ import annotations

from .performance.probes import runtime as _runtime
from .performance.probes.runtime import (
    ACCEPTED_HEADER_SHA256,
    ACCEPTED_SOURCE_SHA256,
    HEADER_RELATIVE,
    SOURCE_RELATIVE,
    AnalyzeProbe,
    InstrumentSource,
    ProbeRuntimeError,
    SelfTest,
    restore_probe,
    run_managed_probe,
    self_test,
    sha256_bytes,
    sha256_file,
)
from .cli.commands.performance import transport_probe_main as main

__all__ = [
    "ACCEPTED_HEADER_SHA256",
    "ACCEPTED_SOURCE_SHA256",
    "HEADER_RELATIVE",
    "SOURCE_RELATIVE",
    "AnalyzeProbe",
    "InstrumentSource",
    "ProbeRuntimeError",
    "SelfTest",
    "main",
    "restore_probe",
    "run_managed_probe",
    "self_test",
    "sha256_bytes",
    "sha256_file",
]


def __getattr__(name: str):
    """Forward legacy private or incidental attribute access to the canonical runtime."""

    return getattr(_runtime, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_runtime)))
