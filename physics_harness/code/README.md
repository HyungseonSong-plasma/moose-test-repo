# Code lifecycle namespace

This package reserves language-agnostic responsibilities for code in the entire
`moose-test-repo` repository. It is not limited to C++, Python, MOOSE inputs, or
Physics source files.

| Package | Responsibility |
| --- | --- |
| `graph/` | Shared contextual graph: node, edge, evidence, claim, scope, context |
| `analysis/` | Code understanding and evidence collection |
| `review/` | Findings and change recommendations |
| `refactor/` | Refactoring plans and approved transformations |
| `delete/` | Deletion plans and approved removal workflows |
| `verification/` | Change verification and evidence evaluation |

The approved [Code Graph v0.1 contract](graph/README.md) models a directed
multigraph: canonical nodes/edges retain their identities, while arbitrary
contexts define dynamic parent-child hierarchy views. Multiple parents,
parallel relations, and cycles are valid. Context traversal reports cycle
references, shared occurrences, or truncation without altering the graph.

Evidence provenance and scoped, conditional Claims are separate responsibilities:
one piece of evidence can inform multiple claims, and a claim can reference
supporting, refuting, or qualifying evidence. Transition plans and approvals
remain separate from both raw graph facts and claim assessments.

This structure adds **package boundaries and a design contract only**.
There are no executable graph operations, code-change permissions, runtime
evidence claims, or automatic deletion paths. Existing
`physics_harness/analysis/`, FDEG collectors, command routing, and
scientific validation remain unchanged. Future implementations should reuse
existing harness execution/evidence capabilities rather than duplicating them.
