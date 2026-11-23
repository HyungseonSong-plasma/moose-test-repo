"""Compatibility re-export; implementation lives in analysis.adapters."""

from .adapters.understandability_interpretation import interpret_understandability_indicators

__all__ = ["interpret_understandability_indicators"]
