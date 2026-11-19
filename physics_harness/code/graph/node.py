"""Context-independent code graph entity identity and source locations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from collections.abc import Mapping

from ._validation import (
    frozen_mapping,
    nonempty,
    optional_nonempty,
    string_tuple,
)


@dataclass(frozen=True, slots=True)
class SourceLocation:
    path: str
    start_line: int | None = None
    end_line: int | None = None

    def __post_init__(self) -> None:
        nonempty(self.path, "location.path")
        for name in ("start_line", "end_line"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError(f"location.{name} must be a positive integer")
        if self.end_line is not None and self.start_line is None:
            raise ValueError("end_line requires start_line")
        if self.end_line is not None and self.end_line < self.start_line:
            raise ValueError("end_line must not precede start_line")


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    kind: str
    name: str
    qualified_name: str | None = None
    language: str | None = None
    location: SourceLocation | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict, hash=False)
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("id", "kind", "name"):
            nonempty(getattr(self, name), f"node.{name}")
        optional_nonempty(self.qualified_name, "node.qualified_name")
        optional_nonempty(self.language, "node.language")
        if self.location is not None and not isinstance(self.location, SourceLocation):
            raise TypeError("node.location must be a SourceLocation or None")
        object.__setattr__(self, "attributes", frozen_mapping(self.attributes, "node.attributes"))
        string_tuple(self.evidence_ids, "node.evidence_ids")
