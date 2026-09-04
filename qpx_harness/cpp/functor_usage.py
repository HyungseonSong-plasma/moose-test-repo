"""Deprecated compatibility facade for MOOSE C++ source observation.

Canonical owner: :mod:`qpx_harness.observation.source_code.moose`.
"""
from qpx_harness.observation.source_code.moose import (
    CPP_TEXT_SUFFIXES,
    FunctorInspectionError,
    extract_functor_property_declaration,
    parameter_functor_calls,
)

__all__ = [
    "CPP_TEXT_SUFFIXES", "FunctorInspectionError",
    "extract_functor_property_declaration", "parameter_functor_calls",
]
