"""Strategy-neutral alternative review using source-bound planning evidence."""

from __future__ import annotations

from dataclasses import dataclass

from .planning import (
    ConstraintCheck, PlanValidation, PlanningAlternative, PlanningContext,
    validate_alternative,
)


@dataclass(frozen=True, slots=True)
class AlternativeReview:
    """Independent alternative reviews; no hidden ranking or strategy policy."""

    results: tuple[PlanValidation, ...]
    recommended_id: None = None  # context-specific selection is not a code invariant

    @property
    def mutation_approved(self) -> bool:
        return False


def review_alternatives(
    context: PlanningContext,
    alternatives: tuple[PlanningAlternative, ...],
    *,
    constraint_checks: tuple[ConstraintCheck, ...] = (),
) -> AlternativeReview:
    if not isinstance(alternatives, tuple) or any(
        not isinstance(item, PlanningAlternative) for item in alternatives
    ):
        raise TypeError("INVALID_PLANNING_ALTERNATIVES")
    ids = [item.id for item in alternatives]
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_PLANNING_ALTERNATIVE")
    if not isinstance(context, PlanningContext):
        raise TypeError("PLANNING_CONTEXT_REQUIRED")
    if not isinstance(constraint_checks, tuple) or any(
        not isinstance(check, ConstraintCheck) for check in constraint_checks
    ):
        raise TypeError("INVALID_CONSTRAINT_CHECKS")
    if set(check.alternative_id for check in constraint_checks) - set(ids):
        raise ValueError("CHECK_FOR_UNKNOWN_ALTERNATIVE")

    results = tuple(
        validate_alternative(context, item, constraint_checks=tuple(
            check for check in constraint_checks if check.alternative_id == item.id
        ))
        for item in alternatives
    )
    return AlternativeReview(results=results)


__all__ = ["AlternativeReview", "review_alternatives"]
