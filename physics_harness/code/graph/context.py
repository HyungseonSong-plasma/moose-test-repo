"""Dynamic contexts and cycle-safe hierarchy views (v0.1 design boundary).

Contexts select roots, relations, direction, evidence filters, scope, and
traversal budgets. Names are not a fixed enum; selected relation semantics
must be explicit. Each context projects the canonical directed multigraph
into a directed subgraph, optionally unfolded as a rooted hierarchy.

Each appearance has an occurrence identity while keeping its canonical node
identity. Multiple parents and parallel paths are permitted. On a repeated
node within the active ancestor path, show a CYCLE_REF without expanding that
path. Nodes reached on other paths remain valid (possibly SHARED_REF).
Budget cutoffs are TRUNCATED and cannot imply complete exploration. Optional
SCC summaries must never replace underlying nodes or edges.

No context schema, projection engine, or renderer is implemented.
"""
