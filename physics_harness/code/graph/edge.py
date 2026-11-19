"""Directed multigraph semantic edge definitions (v0.1 design boundary).

Edges preserve original source -> destination, relation type, identity, and
evidence. Parallel edges, multiple inbound edges, self-loops, and cycles are
valid. A context can project selected edges to parent-child navigation with
its chosen direction; the projection never changes the semantic edge itself.

No graph edge classes or operations are implemented.
"""
