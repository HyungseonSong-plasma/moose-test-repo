# Code lifecycle namespace

This package reserves language-agnostic responsibilities for code in the entire
`moose-test-repo` repository. It is not limited to C++, Python, MOOSE inputs, or
Physics source files.

| Package | Responsibility |
| --- | --- |
| `analysis/` | Code understanding and evidence collection |
| `review/` | Findings and change recommendations |
| `refactor/` | Refactoring plans and approved transformations |
| `delete/` | Deletion plans and approved removal workflows |
| `verification/` | Change verification and evidence evaluation |

This commit adds **package structure only**. There are no executable operations,
code-change permissions, runtime evidence claims, or automatic deletion paths.
Existing `physics_harness/analysis/`, FDEG collectors, command routing, and
scientific validation remain unchanged. Future implementations should reuse
existing harness execution/evidence capabilities rather than duplicating them.
