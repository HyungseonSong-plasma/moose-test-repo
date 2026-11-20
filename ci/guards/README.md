# Repository CI guards

This directory owns repository-specific static and architecture validation.

Boundary:

```text
chatgpt-operation/skills/  reusable operational skills shared across repositories
ci/guards/                 moose-test-repo-specific CI/static architecture guards
physics_harness/           product/runtime/scientific harness
```

Guards may inspect repository files and may import stable `physics_harness` APIs when an integration contract must be checked. Production `physics_harness` code must not import, invoke, or otherwise depend on repository `ci` utilities; that reverse dependency is machine-checked by `physics_dependency_guard.py --check repository`.

These scripts are developer/CI utilities, not user-facing Physics commands and not owners of runtime or scientific semantics.

## #743 — dependency-Guard parity gate

The repository's dependency rules now live in
`ci/contracts/harness_dependencies.json`. The read-only source checker is
`physics_harness.code.verification.dependencies`, invoked by the thin
`ci/guards/verify_harness_dependencies.py` CI wrapper.

Until source-bound parity tests and exact-HEAD Repository CI pass, the historical
`physics_dependency_guard.py` selectors remain as independent gates. A PASS
from this static audit does not prove runtime, dynamic imports, semantic
compatibility, or authorize repository mutation.
