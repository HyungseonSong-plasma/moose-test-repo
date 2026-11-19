"""Context-defined hierarchy views over a shared code graph (reserved).

A context is a query/view specification, not a predefined fixed node hierarchy.
It selects roots, semantic edge types, traversal direction, source scope,
evidence filters, and exploration limits. For example, a CALL context projects
CALLS edges into parent -> child relationships for that view.

A displayed parent-child occurrence refers to a canonical node ID. A node may
have several parents and appear in several paths without being copied.
A hierarchy projection may unfold a cyclic graph for display, but it must
stop expansion on a node already in the active ancestor path and expose a
cycle reference rather than silently dropping the original edge. A node
encountered through a different path remains a valid shared reference.

The underlying graph retains its semantic edges and possible cycles.
No context schema, traversal engine, or renderer is implemented here.
"""
