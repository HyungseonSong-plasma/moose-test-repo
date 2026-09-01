"""Compatibility surface for the canonical C++ call helpers.

The implementation now lives in :mod:`qpx_harness.cpp.calls`.
Legacy imports and module execution remain valid during the compatibility-first package migration.
"""

from __future__ import annotations

from .cpp import calls as _calls
from .cpp.calls import CallArguments, CppCallError, self_test, split_call_arguments

__all__ = [
    "CallArguments",
    "CppCallError",
    "split_call_arguments",
    "self_test",
]


def __getattr__(name: str):
    """Forward legacy private or incidental attribute access to the canonical calls module."""

    return getattr(_calls, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_calls)))


if __name__ == "__main__":
    raise SystemExit(self_test())
