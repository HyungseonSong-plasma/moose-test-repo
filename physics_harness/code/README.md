# Code lifecycle namespace

This package provides language-agnostic foundations for code across the entire
`moose-test-repo\` repository, including C++, Python, Fortran, MOOSE inputs,
workflow definitions, and other supported sources.

| Package | Responsibility |
| --- | --- |
| \`graph/\` | Shared graph records: node, edge, evidence, claim, scope, context |
| \`diagnostics/\` | Evidence collection and code fact extraction (reserved) |
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

The general Repository CI ignores harness-code-only changes; the SOL
Integration workflow is restricted to ontology/runtime-integration changes.
Mixed-scope pull requests still receive the applicable broader validation.
