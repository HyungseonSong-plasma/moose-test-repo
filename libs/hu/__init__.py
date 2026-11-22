"""Compatibility namespace for historical Human Understandability consumers.

New integrations should import from libs.code_understandability.
"""

from .evaluation import HUComparison, MetricDifference, compare_hu, evaluate_hu
from .metrics import derive_hu_indicators, from_python_ast
from .model import (
    HUAssessment, HUIndicator, HUInput, HUObservation, ObservedHU, StructuralMetric,
)

__all__ = [
    "HUAssessment", "HUComparison", "HUIndicator", "HUInput", "HUObservation",
    "MetricDifference", "ObservedHU", "StructuralMetric", "compare_hu",
    "evaluate_hu", "derive_hu_indicators", "from_python_ast",
]
