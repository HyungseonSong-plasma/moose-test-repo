# Code Graph v0.1 — Contextual Directed Multigraph

**Status:** immutable Python data records, snapshot reference validation, and
bounded context unfolding implemented. Language parsers, native execution,
semantic claim assessment, FDEG adapters, and code mutation are **not**
implemented. Applies across languages and file types in `moose-test-repo`;
not a FDEG migration or retirement authorization.

## Canonical graph

`G = (V, E)` is a **directed multigraph**. Multiple semantic edges may connect
the same node pair. Multiple inbound edges, self-loops, and cycles are valid.
Never rewrite it into a tree or discard edges to simplify rendering.

- **Node:** context-independent identity for a code entity or resource. No
  mandatory `parent_id` or fixed repository/folder/file/class/function depth.
- **Edge:** directed semantic relation with identity, source and destination
  nodes, relation type, and evidence. Relations such as `CALLS`, `CONTAINS`,
  `DEFINES`, `IMPORTS`, `REFERENCES` remain distinct.
- **Evidence:** a source or observation record: what was collected, provenance,
  method, scope, and observed/inferred/unresolved strength. Evidence is **not**
  a verdict or proof that a transition was executed.
- **Claim:** a separately identified, scoped and conditional assertion about
  graph subject(s). Its evaluation refers to evidence with explicit roles
  (e.g. `SUPPORTS`, `REFUTES`, `QUALIFIES`) and assessment status. Claims do
  not modify the graph and an assessment is not automatically execution approval.
- **Scope:** exact analyzed revision, included/excluded source surfaces, scan
  and observation boundaries, unresolved dependencies, and completeness state.

## Evidence and Claim separation

`evidence.py` owns provenance; `claim.py` owns assertions and their evaluation
boundary. The relationship is many-to-many. An Evidence record can inform
multiple Claims, and a Claim can reference supporting, refuting, or qualifying
Evidence. Opposing evidence must be retained rather than silently collapsed.

Implemented, frozen Python model constructors (shown with core fields):

- `Evidence(id, kind, source_ref, method, scope_id, observation_status, attributes)`
- `Claim(id, predicate, subject_refs, scope_id, conditions, evidence_refs, assessment_status)`
- `ClaimEvidenceRef(evidence_id, role)`, nested under its owning Claim
- `GraphSnapshot(scope, nodes, edges, evidence, claims)` validates all references

Distinguish evidence acquisition (`SOURCE_DECLARED`, `INFERRED`,
`RUNTIME_OBSERVED`, `UNRESOLVED`) from claim assessment
(`SUPPORTED`, `REFUTED`, `UNRESOLVED`, `NOT_EVALUATED`).
A source-backed conditional functional claim is not a native verification
result; a plan-review PASS is not a retirement or scientific PASS.

This supports existing FDEG families without conflating them:

| FDEG family | Graph role | Evidence/Claim role |
| --- | --- | --- |
| Structural | Code entities and declared dependencies | Source-pinned evidence; claims limited by observed scope |
| Functional | Functional subjects, contracts, candidate relations | Conditional semantic/preservation claims, alternative comparisons, required discriminators |
| Transition | Proposed change/dependency relations belong to a plan overlay | Proposed options, open obligations, and validation claims; **not** executed changes |

Actual `steps`, `blocking_obligations`, and `candidate_rewiring_options`
need a change/plan representation rather than silently becoming canonical
code edges. FDEG report conversion and validation remain future work.

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

## Minimal context specification (illustrative JSON)

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
`evidence.py` provenance, `claim.py` assertions and assessment,
`scope.py` analysis completeness, and `context.py` projection/navigation.
`GraphSnapshot` validates subject, endpoint, evidence, and scope references;
`unfold_context` implements bounded, path-local cycle-safe hierarchy display.
No parser, claim evaluator, automatic graph-ID match, native observation,
transition-plan execution, or FDEG report adapter is implemented.


## Implemented Python interfaces and boundaries

Import from `physics_harness.code.graph`:

- `SourceLocation`, `Node`, `RelationSpec`, `Edge`
- `Evidence`, `ClaimEvidenceRef`, `Claim`
- `Scope`, `GraphSnapshot`
- `RelationSelector`, `Context`, `NodeOccurrence`, `HierarchyView`,
  `unfold_context(snapshot, context)`

The data classes are frozen and their JSON-shaped attributes/conditions
recursively converted to immutable mappings and tuples. Snapshot endpoints
must resolve to canonical Nodes; missing/external targets need an explicit
`Node(kind="unresolved", ...)`. Duplicate IDs, missing Evidence/Claim subjects,
cross-scope records, and contradictory COMPLETE+unresolved scope are rejected.

Scope currently accepts an exact 40-character Git SHA-1; it does not fetch or
attest the repository itself. `COMPLETE` is a supplied scan assertion, **not**
independently verified by `GraphSnapshot`. Context evidence filters are
observation-status filters; they never promote static records to runtime facts.

`unfold_context` keeps the canonical graph unchanged, makes a distinct
occurrence for each traversed edge path, returns `CYCLE_REF` on path-local
cycles, annotates cross-path nodes as shared, and explicitly marks
`TRUNCATED` on a depth/occurrence budget boundary. No SCC consolidation or
semantic equivalence decision is performed.

P0 tests live under `physics_harness/code/tests/` and run with:

```bash
python3 -m unittest discover -s physics_harness/code/tests -p 'test_graph_*.py' -v
```
