"""Solver-independent Research Mode v0.1 goal and evaluation-scope vocabulary.

This is a human-scoped question contract, not an LLM judge of scientific
sufficiency and not a change to ExperimentSpec schema version 2.
"""
from __future__ import annotations

from dataclasses import dataclass

EVALUATION_SCOPES = {
    "full_field": "Compare an entire spatial/temporal field using an explicitly chosen error metric.",
    "representative_profiles": "Compare preselected physically representative cuts or profiles.",
    "key_features": "Compare peaks, locations, widths or other declared physical features.",
    "combined": "Compare complementary field, profile and feature evidence.",
    "custom": "Use a human-specified alternative evaluation boundary.",
}


@dataclass(frozen=True)
class ResearchObjective:
    statement: str
    evaluation_scope: str
    scope_detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.statement, str) or not self.statement.strip():
            raise ValueError("research objective must be non-empty")
        if not isinstance(self.evaluation_scope, str) or self.evaluation_scope not in EVALUATION_SCOPES:
            raise ValueError("unknown evaluation scope; choose a declared scope or custom")
        if self.evaluation_scope == "custom" and (
            not isinstance(self.scope_detail, str) or not self.scope_detail.strip()
        ):
            raise ValueError("custom scope requires an explicit human scope detail")
        if self.scope_detail is not None and (
            not isinstance(self.scope_detail, str) or not self.scope_detail.strip()
        ):
            raise ValueError("scope detail must be non-empty when supplied")


def scope_choices() -> list[dict[str, str]]:
    return [{"id": k, "description": v} for k, v in EVALUATION_SCOPES.items()]


__all__ = ["ResearchObjective", "EVALUATION_SCOPES", "scope_choices"]
