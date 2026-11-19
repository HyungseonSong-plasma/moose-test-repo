# Code lifecycle namespace

This package reserves language-agnostic responsibilities for code in the entire
`moose-test-repo` repository. It is not limited to C++, Python, MOOSE inputs, or
Physics source files.

| Package | Responsibility |
| --- | --- |
| `graph/` | Shared code graph boundary: node, edge, evidence, scope, context |
| `analysis/` | Code understanding and evidence collection |
| `review/` | Findings and change recommendations |
| `refactor/` | Refactoring plans and approved transformations |
| `delete/` | Deletion plans and approved removal workflows |
| `verification/` | Change verification and evidence evaluation |

The graph's canonical node IDs are independent of their displayed hierarchy.
`graph/context.py` reserves dynamic context-defined parent-child projections:
different source, call, or impact views may show the same node under several
parents. Cyclic edges are preserved in the graph and exposed as references
when an individual hierarchy view would recurse indefinitely.

This structure adds **package boundaries only**. There are no executable operations,
code-change permissions, runtime evidence claims, or automatic deletion paths.
Existing `physics_harness/analysis/`, FDEG collectors, command routing, and
scientific validation remain unchanged. Future implementations should reuse
existing harness execution/evidence capabilities rather than duplicating them.
