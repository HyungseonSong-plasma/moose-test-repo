"""Internal dependency bridge from the MOOSE adapter to generic C++ parsing.

Dependency direction is intentionally adapter -> generic observation. New code
should import generic C++ helpers from ``qpx_harness.observation.source_code.cpp``
directly; this bridge exists only to preserve the moved source-inspection module
without changing its parsing behavior in WB3.
"""
from qpx_harness.observation.source_code.cpp import CppSource, CppSourceError, split_call_arguments

__all__ = ["CppSource", "CppSourceError", "split_call_arguments"]
