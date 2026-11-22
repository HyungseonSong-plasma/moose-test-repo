"""Legacy model symbols; use libs.code_understandability.model."""

from libs.code_understandability.model import (
    HumanObservation as HUObservation,
    ObservedHumanResponse as ObservedHU,
    StructuralMetric,
    UnderstandabilityAssessment as HUAssessment,
    UnderstandabilityIndicator as HUIndicator,
    UnderstandabilityInput as HUInput,
)

__all__ = [
    "HUAssessment", "HUIndicator", "HUInput", "HUObservation",
    "ObservedHU", "StructuralMetric",
]
