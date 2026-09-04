"""Deprecated compatibility facade for C++ call observation.

Canonical owner: :mod:`qpx_harness.observation.source_code.cpp`.
"""
from qpx_harness.observation.source_code.cpp import (
    CallArguments,
    CppCallError,
    CppSource,
    CppSourceError,
    Span,
    split_call_arguments,
)

__all__ = [
    "CallArguments", "CppCallError", "CppSource", "CppSourceError", "Span",
    "split_call_arguments",
]
