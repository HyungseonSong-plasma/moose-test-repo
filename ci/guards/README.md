# Repository CI guards

This directory owns repository-specific static and architecture validation.

Boundary:

```text
chatgpt-operation/skills/  reusable operational skills shared across repositories
ci/guards/                 moose-test-repo-specific CI/static architecture guards
physics_harness/           product/runtime/scientific harness
```

Guards may inspect repository files and may import stable `physics_harness` APIs when an integration contract must be checked. Production `physics_harness` code must not import, invoke, or otherwise depend on repository `ci` utilities; that reverse dependency is machine-checked by `verify_harness_dependencies.py` using the repository's declarative dependency contract.

These scripts are developer/CI utilities, not user-facing Physics commands and not owners of runtime or scientific semantics.

## #743 — dependency-Guard parity gate

The repository's dependency rules now live in
`ci/contracts/harness_dependencies.json`. The read-only source checker is
`physics_harness.code.verification.dependencies`, invoked by the thin
`ci/guards/verify_harness_dependencies.py` CI wrapper.

The historical six-selector `physics_dependency_guard.py` CI gate was
retired after the same PR HEAD passed ten old-Guard/Harness equivalence cases,
all six legacy selectors, and the source-bound Harness audit.
Frozen negative controls now reside in
`ci/guards/tests/test_dependency_contract.py` and run in Repository CI.
A PASS from this static audit does not prove runtime, dynamic imports,
semantic compatibility, or authorize repository mutation.

## Repository CI v0.1 (#749)

The integration-only `Repository CI` Workflow runs one unconditional
`validate` Job. `repository_ci_scope.py` and
`ci/contracts/repository_ci_scope_v1.json` record all 17 former Job owners
and the 50 former validation steps. Physics tests, Native P1/P2 and the
manual Artifact API probe moved to separate authorized Workflows without
changing the underlying scientific or Source Evidence obligations.
See `ci/REPOSITORY_INTEGRATION_CONTRACT.md`.
