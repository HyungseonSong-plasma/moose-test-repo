"""Deprecated compatibility facade for generic C++ source observation.

Canonical owner: :mod:`qpx_harness.observation.source_code.cpp`.
No new semantic responsibility may be added here.
"""
from qpx_harness.observation.source_code.cpp import CppSource, CppSourceError, Span, mask_cpp

__all__ = ["CppSource", "CppSourceError", "Span", "mask_cpp"]
