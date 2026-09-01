"""Compatibility surface for the canonical C++ source scanner.

The implementation now lives in :mod:`qpx_harness.cpp.source`.
Legacy imports remain valid during the compatibility-first package migration.
"""

from __future__ import annotations

from .cpp import source as _source
from .cpp.source import CppSource, CppSourceError, Span, mask_cpp, self_test

__all__ = [
    "CppSource",
    "CppSourceError",
    "Span",
    "mask_cpp",
    "self_test",
]


def __getattr__(name: str):
    """Forward legacy private or incidental attribute access to the canonical source module."""

    return getattr(_source, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_source)))
