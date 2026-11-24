"""Typed, directed semantic relations; parallel edges and cycles are valid."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ._validation import frozen_mapping, nonempty, optional_nonempty, string_tuple


@dataclass(frozen=True, slots=True)
class RelationSpec:
    id: str
    description: str
    source_role: str
    target_role: str

    def __post_init__(self) -> None:
        for name in ("id", "description", "source_role", "target_role"):
            nonempty(getattr(self, name), f"relation.{name}")


@dataclass(frozen=True, slots=True)
class Edge:
    id: str
    source_id: str
    target_id: str
    relation: str
    discriminator: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict, hash=False)
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("id", "source_id", "target_id", "relation"):
            nonempty(getattr(self, name), f"edge.{name}")
        optional_nonempty(self.discriminator, "edge.discriminator")
        object.__setattr__(self, "attributes", frozen_mapping(self.attributes, "edge.attributes"))
        string_tuple(self.evidence_ids, "edge.evidence_ids")
