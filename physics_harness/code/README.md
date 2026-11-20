# Code lifecycle namespace

This package provides language-agnostic foundations for code across the entire
`moose-test-repo\` repository, including C++, Python, Fortran, MOOSE inputs,
workflow definitions, and other supported sources.

| Package | Responsibility |
| --- | --- |
| \`graph/\` | Shared graph records: node, edge, evidence, claim, scope, context |
| [diagnostics/](diagnostics/README.md) | Source-bound fact extraction and incomplete-coverage reporting (D1–D5) |
| \`analysis/\` | Code review, findings, quality/impact analysis (reserved) |
| \`refactor/\` | Approved refactoring plans and changes (reserved) |
| \`delete/\` | Approved code-retirement and deletion (reserved) |
| \`verification/\` | Pre/post-change structural and semantic verification (reserved) |
| \`tests/\` | Local graph and lifecycle P0 self-tests |

The approved [Code Graph v0.1](graph/README.md) is a directed multigraph:
canonical nodes and edges have identities independent of contexts. A context
creates a parent-child hierarchy view, allowing multiple parents, cycles,
parallel edges, and deterministic bounded traversal with cycle references.

Evidence and Claim are separate, many-to-many concepts. Evidence stores
provenance and observation status; a Claim asserts a conditional predicate,
references evidence with a support/refute/qualify role, and retains an explicit
assessment status. Assessments are not permissions for code mutation.

The implemented v0.1 surface is the **graph data model, snapshot referential
integrity validation, and context hierarchy unfolding only**. No language
parsers, FDEG report adapters, automated refactoring/deletion, native runtime
evidence, or physics acceptance were added. Existing FDEG and Physics
implementations and the existing \`physics_harness/analysis/\` remain unchanged.

## Harness Code CI

Only `physics_harness/code/tests/` is in the `Harness Code CI` scope.
The dedicated workflow `.github/workflows/harness-code.yml` runs on
changes to `physics_harness/code/**` (or its workflow file) and executes:

```bash
python -m pytest -q physics_harness/code/tests
```

Repository CI verifies the shared integration contract for every PR,
including Harness-only changes. `Harness Code CI` owns these local pytest
tests; domain Physics/Native workflows run only for their declared affected
source scopes. SOL Integration retains its separate runtime-integration scope.

## Diagnostics v0.1

The read-only [Diagnostics core](diagnostics/README.md) connects exact Git
source/blob provenance, pluggable collectors, deterministic GraphSnapshot
assembly and scoped completeness receipts. The first collector reads Workflow
YAML as static declarations, **not** actual GitHub Actions executions.
