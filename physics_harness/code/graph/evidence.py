"""Evidence provenance: observations are not verdicts or semantic claims."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ._validation import frozen_mapping, nonempty


OBSERVATION_STATUSES = frozenset({
    "SOURCE_DECLARED", "INFERRED", "RUNTIME_OBSERVED", "UNRESOLVED",
})


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    kind: str
    source_ref: str
    method: str
    scope_id: str
    observation_status: str = "SOURCE_DECLARED"
    attributes: Mapping[str, Any] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        for name in ("id", "kind", "source_ref", "method", "scope_id"):
            nonempty(getattr(self, name), f"evidence.{name}")
        if self.observation_status not in OBSERVATION_STATUSES:
            raise ValueError(f"unknown observation status: {self.observation_status!r}")
        object.__setattr__(
            self, "attributes", frozen_mapping(self.attributes, "evidence.attributes")
        )
