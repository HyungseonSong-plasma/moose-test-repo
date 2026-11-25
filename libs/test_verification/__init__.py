"""Shared test observations and comparison; no domain acceptance policy."""
from .junit import parse_junit, compare_case_outcomes
from .pytest_runner import PytestRun, run_pytest

__all__ = ["parse_junit", "compare_case_outcomes", "PytestRun", "run_pytest"]
