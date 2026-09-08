# Issue 128 — QPX issue/campaign namespace census

## Decision

Long-lived production ownership under `qpx_harness/` is capability-oriented. Issue identity remains valid in `recipes/`, `experiments/`, tests, documentation, and repository history, but generic production behavior must not remain owned by `qpx_harness/issue*` or `qpx_harness/coupling_evr*` namespaces.

The current declarative experiment registry contains eight protocols and none resolves through the Issue43/45/46 or `coupling_evr1/2` production namespaces. Those namespaces are therefore compatibility/historical surfaces rather than current experiment-gateway owners.

## Census and disposition

| Production surface | Current exposure | Canonical owner / preserved source | Disposition |
| --- | --- | --- | --- |
| `qpx_harness/issue43_coupling/` | legacy Issue43 diagnostic composition and historical guard | `evidence`, `diagnose`, `moose`, `petsc`; scientific policy in `recipes/issue43_*` | DELETE_AFTER_CALLER_MIGRATION |
| `qpx_harness/issue43_coupling_diagnostic.py` | legacy CLI facade | canonical capabilities plus Issue43 recipes | DELETE_AFTER_CALLER_MIGRATION |
| `qpx_harness/issue43_fast_*.py` | historical Issue43/44 compatibility surface | `recipes/issue43_feedback_basis.py`, canonical MOOSE/output/execution capabilities | DELETE_AFTER_CALLER_MIGRATION |
| `qpx_harness/issue43_relaxation_runtime.py` | historical runtime/equivalence support | accepted feedback semantics in Issue43 recipes; reusable mechanics in canonical capabilities | DELETE_AFTER_CALLER_MIGRATION |
| `qpx_harness/issue45/` | compatibility adapters | `qpx_harness/inventory/` plus `recipes/issue45_*` | DELETE_AFTER_CALLER_MIGRATION |
| `qpx_harness/issue45_first_linear.py` | compatibility facade | `qpx_harness.inventory.cli:first_linear_main` | DELETE_AFTER_CALLER_MIGRATION |
| `qpx_harness/electron_inventory_nullspace.py` | pre-canonical compatibility facade | `qpx_harness.inventory` | DELETE_AFTER_CALLER_MIGRATION |
| `qpx_harness/issue46_fd_reference.py` | legacy Issue46 CLI diagnostic | historical diagnostic; generic PETSc/inventory primitives already capability-owned | DELETE_AFTER_CALLER_MIGRATION |
| `qpx_harness/issue46_jacobian_localization.py` | legacy Issue46 CLI diagnostic | historical diagnostic; generic PETSc/inventory primitives already capability-owned | DELETE_AFTER_CALLER_MIGRATION |
| `qpx_harness/coupling_evr1/` | legacy Issue31 campaign CLI | current R3/R4 declarative protocols; historical evidence remains in experiments/history | DELETE_AFTER_CALLER_MIGRATION |
| `qpx_harness/coupling_evr2/` | legacy Issue31 campaign CLI | current R3/R4 declarative protocols; historical evidence remains in experiments/history | DELETE_AFTER_CALLER_MIGRATION |

`qpx_harness/scale_audit.py` is retained for now with explicit justification: although born during Issue43, its module identity is capability-oriented and the current legacy CLI exposes a generally named `scale-audit` operation. A future issue may move it into a dedicated analysis/diagnostic package if that improves ownership, but Issue 128 does not rename a live generic surface solely for historical provenance.

## Caller migration

The legacy CLI routes `coupling-evr1`, `coupling-evr2`, `fast-relaxation`, `fast-coupling-diagnostic`, `inventory-jacobian-localization`, and `inventory-fd-reference` are retired. `inventory-nullspace` and `inventory-first-linear` remain because they already resolve directly to the canonical `qpx_harness.inventory.cli` owner.

The Issue43/45 science-refactor guard no longer imports issue-numbered QPX facades. It now verifies the canonical recipe ownership, Evidence → Diagnose capability path, canonical inventory package, and PETSc residual-fidelity contract directly.

## Guard policy

`tools/qpx_architecture_census.py` rejects Python production ownership at top-level paths matching:

```text
qpx_harness/issue*/
qpx_harness/issue*_*.py
qpx_harness/coupling_evr*/
qpx_harness/coupling_evr*_*.py
```

The restriction intentionally does not apply to `recipes/`, `experiments/`, tests, docs, or archive/history because issue identity is legitimate scientific provenance there.

## Scientific invariants

This cleanup does not change accepted physics formulas, thresholds, case definitions, or current declarative protocol semantics. Issue43 accepted feedback semantics remain recipe-owned; Issue45 inventory behavior remains capability-owned by `qpx_harness/inventory`; current R3/R4 experiments continue to resolve through the declarative protocol registry.
