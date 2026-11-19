"""Code graph semantic relationships and context projections (reserved).

Underlying directed edges retain their own meaning: CALLS, DEFINES, IMPORTS,
REFERENCES, and so on. A context selects relevant edges and projects them into
parent -> child relationships for its hierarchy view, including a CALL context
where caller -> callee forms the displayed hierarchy.

Parent-child is a context-specific interpretation, not an intrinsic node
property or proof of unique ownership. Multiple parents and cycles are valid
in the graph and must be preserved. Static candidates are not observed
runtime activity.

No edge model or traversal is implemented in this scaffold.
"""
