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
