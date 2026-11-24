"""Claims are scoped, conditional assessments with role-labelled evidence links."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ._validation import frozen_mapping, instance_tuple, nonempty, string_tuple


CLAIM_STATUSES = frozenset({
    "NOT_EVALUATED", "SUPPORTED", "REFUTED", "QUALIFIED", "UNRESOLVED",
})
EVIDENCE_ROLES = frozenset({"SUPPORTS", "REFUTES", "QUALIFIES"})


@dataclass(frozen=True, slots=True)
class ClaimEvidenceRef:
    evidence_id: str
    role: str

    def __post_init__(self) -> None:
        nonempty(self.evidence_id, "claim_evidence.evidence_id")
        if self.role not in EVIDENCE_ROLES:
            raise ValueError(f"unknown claim evidence role: {self.role!r}")


@dataclass(frozen=True, slots=True)
class Claim:
    id: str
    predicate: str
    subject_refs: tuple[str, ...]
    scope_id: str
    conditions: Mapping[str, Any] = field(default_factory=dict, hash=False)
    evidence_refs: tuple[ClaimEvidenceRef, ...] = ()
    assessment_status: str = "NOT_EVALUATED"

    def __post_init__(self) -> None:
        for name in ("id", "predicate", "scope_id"):
            nonempty(getattr(self, name), f"claim.{name}")
        string_tuple(self.subject_refs, "claim.subject_refs")
        if not self.subject_refs:
            raise ValueError("claim.subject_refs must not be empty")
        object.__setattr__(self, "conditions", frozen_mapping(self.conditions, "claim.conditions"))
        instance_tuple(self.evidence_refs, ClaimEvidenceRef, "claim.evidence_refs")
        if len({(link.evidence_id, link.role) for link in self.evidence_refs}) != len(
            self.evidence_refs
        ):
            raise ValueError("duplicate claim evidence link")
        if self.assessment_status not in CLAIM_STATUSES:
            raise ValueError(f"unknown claim assessment status: {self.assessment_status!r}")
        if self.assessment_status in {"SUPPORTED", "REFUTED", "QUALIFIED"} and not self.evidence_refs:
            raise ValueError("assessed claim requires evidence links")
