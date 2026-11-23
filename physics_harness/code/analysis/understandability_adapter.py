"""Compatibility re-exports; implementation lives in analysis.adapters."""

from .adapters.understandability_adapter import (
    assess_code_understandability, summarize_understandability,
)

__all__ = ["assess_code_understandability", "summarize_understandability"]
