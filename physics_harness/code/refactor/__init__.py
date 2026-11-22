"""Strategy-neutral code improvement planning using source-bound evidence."""

from .alternatives import AlternativeReview, review_alternatives
from .naming import (
    ExtractionUnit, NamingCase, NamingEvidence, NamingOption, NamingOptionReview,
    review_naming_option, to_planning_alternative,
    NamingRecommendation, RejectedNamingCandidate, NamingDecisionReceipt,
    build_naming_recommendation_brief, adjudicate_naming_recommendation,
)
from .evolution import (
    DeclaredClass, DeclaredFunction, ImportedSymbol, SourceStructure,
    DelegationSeam, HistoryDelta, NamingEvolutionReceipt,
    observe_python_structure, compare_source_history,
    find_delegation_seams, audit_source_evolution, audit_git_history,
)
from .planning import (
    ConstraintCheck, HardConstraint, PlanValidation, PlanningAlternative,
    PlanningAssessment, PlanningContext, build_planning_context,
    validate_alternative,
)

__all__ = [
    "AlternativeReview", "ConstraintCheck", "HardConstraint", "PlanValidation",
    "PlanningAlternative", "PlanningAssessment", "PlanningContext",
    "build_planning_context", "review_alternatives", "validate_alternative",
    "DeclaredClass", "DeclaredFunction", "ImportedSymbol", "SourceStructure",
    "DelegationSeam", "HistoryDelta", "NamingEvolutionReceipt",
    "observe_python_structure", "compare_source_history", "find_delegation_seams",
    "audit_source_evolution", "audit_git_history",
    "NamingEvidence", "NamingCase", "ExtractionUnit", "NamingOption",
    "NamingOptionReview", "review_naming_option", "to_planning_alternative",
    "NamingRecommendation", "RejectedNamingCandidate", "NamingDecisionReceipt",
    "build_naming_recommendation_brief", "adjudicate_naming_recommendation",
]
