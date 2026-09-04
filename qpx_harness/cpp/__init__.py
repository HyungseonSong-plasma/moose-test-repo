"""Deprecated compatibility package.

Canonical responsibility owner: :mod:`qpx_harness.observation.source_code`.
This namespace remains only so existing callers can migrate without semantic or
behavioral change. New production code must not import from ``qpx_harness.cpp``.
"""
from qpx_harness.observation import source_code

from . import calls, functor_usage, source

__all__ = ["calls", "functor_usage", "source", "source_code"]
