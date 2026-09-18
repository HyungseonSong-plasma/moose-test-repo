# Repository guards

This directory owns repository/static architecture validation.

Boundary:

```text
tools/workflow/   repository workflow/control plane
tools/guards/     repository/static architecture guards
physics_harness/  product/runtime/scientific harness
```

Guards may inspect repository files and may import stable `physics_harness` APIs when an integration contract must be checked. Production `physics_harness` code must not import, invoke, or otherwise depend on repository `tools`; that reverse dependency is machine-checked by `physics_dependency_guard.py --check repository`.

These scripts are developer/CI utilities, not user-facing Physics commands and not owners of runtime or scientific semantics.
