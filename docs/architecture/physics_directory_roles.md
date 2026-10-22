# Physics directory roles v0.1

Source of truth: `docs/architecture/physics_directory_roles_v1.json`.
This **current physical namespace** policy complements historical frozen
`qpx_harness.*` semantics and the detailed canonical folder contract.
It explicitly includes the existing `evidence/` and `evaluation/`
packages, which are not present in the older hierarchy illustration.

`ci/guards/physics_directory_role_guard.py` evaluates actual Python AST
imports and specifically declared process-call shapes without executing
source. It reports evidence by exact source and destination and fails CI on
new prohibited edges or undeclared roles. It does not infer runtime imports,
ownership from spelling, or scientific correctness.

Known, reasoned existing exceptions are NOT silently green:
- `application/gateway.py` -> MOOSE adapter: transitional semantic gateway
  prior to SOL cutover; requires review, not permission to add new edges.
- `application/performance.py` -> MOOSE performance implementation: approved
  explicit target-specific operational route, not a generic semantic gateway.
- `ontology/sol_runtime_consumer.py` subprocess call: transitional review for
  ownership of invocation mechanics; upstream SOL runtime itself remains
  upstream-owned.

The existing `physics_dependency_guard.py` continues to own its legacy
category and cycle checks. It now recognizes historical forbidden target
identifiers without accidentally enlarging its cycle graph. This additional
role guard covers *all 15 current* canonical Physics role packages. Any
naming/semantic ambiguity that cannot be proven from AST must be reviewed,
not represented as a conclusive violation or PASS.
