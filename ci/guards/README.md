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

## Issue #743 — evidence-bound dependency-guard consolidation

Repository CI runs `physics_dependency_guard.py --check all` once instead of
reparsing the entire production harness for six separate selectors. The
`evidence`, `analysis`, `execution`, `presentation`, `repository`, and
`cycle` checks remain active. Synthetic positive/negative controls in
`ci/guards/tests/test_physics_dependency_guard.py` prove that the combined
exit verdict is the union of the six individual results.

This is an execution-cost consolidation, **not** retirement of dependency
constraints. Harness Code Verification identifies source provenance and
change-driven follow-up obligations; candidate import/call edges do not prove
resolved dependency direction, application semantics, global consumer closure,
or native runtime compatibility. Do not remove the domain-specific terminology,
numerical-method ownership, campaign, or plasma semantic guards on that basis.
