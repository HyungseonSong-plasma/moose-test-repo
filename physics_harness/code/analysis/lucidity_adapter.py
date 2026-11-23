"""Stable import path; implementation lives in analysis.adapters.lucidity_adapter."""
from .adapters.lucidity_adapter import assess_code_understandability, summarize_understandability

__all__ = ["assess_code_understandability", "summarize_understandability"]
