# Code Graph v0.1 — Contextual Directed Multigraph (design contract)

**Status:** approved conceptual contract; interfaces, parsers, traversal, and
execution are **not implemented**. Applies across languages and file types in
`moose-test-repo`; not a FDEG migration or retirement authorization.

## Canonical graph

`G = (V, E)` is a **directed multigraph**. Multiple semantic edges may connect
the same node pair. Multiple inbound edges, self-loops, and cycles are valid.
Never rewrite it into a tree or discard edges to simplify rendering.

- **Node:** context-independent identity for a code entity or resource. No
  mandatory `parent_id` or fixed repository/folder/file/class/function depth.
- **Edge:** directed semantic relation with identity, source and destination
  nodes, relation type, and evidence. Relations such as `CALLS`, `CONTAINS`,
  `DEFINES`, `IMPORTS`, `REFERENCES` remain distinct.
- **Evidence:** source/line/blob or independent observation references and
  claim strength (declared, inferred, observed, unresolved). Static reachability
  is never automatically runtime observation.
- **Scope:** exact analyzed revision, included/excluded source surfaces, scan
  and observation boundaries, unresolved dependencies, and completeness state.

## Dynamic context

A context is a **query/view specification**, not a predefined taxonomy or a
new copy of the graph. It selects roots, relation filter(s), direction,
scope/evidence filters, and traversal limits. Arbitrary names are allowed
(e.g. `CALL`, `SOURCE`, `DELETE_IMPACT`); names alone do not imply semantics.

For example, a context selecting `CALLS` in the forward direction projects
caller to callee as parent to child for display. A reverse-impact context can
show dependents as children. An edge can be projected in different directions
by different contexts without mutating its original meaning.

A context produces `G_c = (V_c, E_c)`, another directed graph, and can expose
a **rooted hierarchy unfolding** for navigation. The hierarchy is a view,
not an invariant that each node has one parent. Parent-child is a contextual
role of the selected edge; do not persist redundant synthetic hierarchy edges
as canonical facts.

## General handling of repeated nodes and cycles

Preserve all original edges. For hierarchy presentation:

1. Identify canonical `node_id` and `edge_id` independently of the view.
2. Assign each displayed path occurrence an `occurrence_id` associated with
   `context_id` and the traversed path (including edge identity).
3. If a child is **already on the current ancestor path**, show
   `CYCLE_REF` to that canonical node and stop expanding **that path only**.
4. If a node is also reachable by another path, keep that path as a valid
   occurrence; it may be annotated `SHARED_REF`. Do not use a global
   visited-set to suppress other paths.
5. Enforce bounded exploration (e.g. max depth and max occurrences), marking
   cut-off branches `TRUNCATED` with their reason. A truncated view must not
   claim completeness.
6. For graph-level cycle analysis, optional strongly connected components
   (SCCs) may summarize cyclic groups without replacing the underlying graph.

`CYCLE_REF`, `SHARED_REF`, and `TRUNCATED` are **view statuses**, not Node
kinds or replacements for semantic edges. Repeated appearances do not create
new code entities. Analysis and deletion checks may deduplicate by canonical
node identity while still inspecting **all in-scope edge/path obligations**.

## Minimal context specification (illustrative, not an implemented API)

```json
{
  "context_id": "impact-target-001",
  "roots": ["node:target"],
  "relations": ["CALLS", "IMPORTS", "REFERENCES"],
  "direction": "REVERSE",
  "scope": {"revision": "<exact-head>", "coverage": "DECLARED_ONLY"},
  "evidence_filter": "ALL",
  "traversal": {
    "cycle": "REFERENCE",
    "multiple_parent": "ALLOW",
    "max_depth": 10,
    "max_occurrences": 10000
  }
}
```

The schema above is illustrative. New relation names and user-defined contexts
need a documented meaning/selector; an unknown name must not silently imply
a known relation, runtime activation, coverage, or safe deletion.

## Implementation boundaries

`node.py` owns entity identity, `edge.py` semantic relationships,
`evidence.py` provenance, `scope.py` analysis completeness, and
`context.py` projection/navigation contracts. None of these modules currently
provides executable graph traversal or claims that existing FDEG evidence is
automatically equivalent to this model.
