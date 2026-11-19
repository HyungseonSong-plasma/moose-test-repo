"""Context-independent code graph node identity (reserved).

A node represents one code entity and has no intrinsic parent or parent_id.
Hierarchy is not a fixed repository -> folder -> file -> class -> function
chain: the same node can appear under different parents in different contexts.

For example, a function can be a child of its source file in a source view and
of an entry point in an execution view. Context-specific parent-child
relationships belong to edges, not node identity.

No node model or parser is implemented in this scaffold.
"""
