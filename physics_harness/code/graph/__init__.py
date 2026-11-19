"""Language-agnostic Code Graph v0.1 model and bounded hierarchy projection."""

from .claim import Claim, ClaimEvidenceRef
from .context import (
    Context,
    HierarchyView,
    NodeOccurrence,
    RelationSelector,
    unfold_context,
)
from .edge import Edge, RelationSpec
from .evidence import Evidence
from .node import Node, SourceLocation
from .scope import GraphSnapshot, Scope

__all__ = [
    "Claim", "ClaimEvidenceRef", "Context", "Edge", "Evidence",
    "GraphSnapshot", "HierarchyView", "Node", "NodeOccurrence",
    "RelationSelector", "RelationSpec", "Scope", "SourceLocation",
    "unfold_context",
]
