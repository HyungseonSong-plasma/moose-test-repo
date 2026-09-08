# Issue 129 — root `qpx_harness` surface census

## Baseline

Branch: `issue-129-root-surface-cleanup`, created from the stabilized `issue-128-retire-issue-namespaces` state.

The direct Python production surface under `qpx_harness/` contained exactly three non-`__init__.py` modules before migration:

```text
qpx_harness/bundle.py
qpx_harness/evidence_diagnose_smoke.py
qpx_harness/scale_audit.py
```

## Disposition table

| Path | Live callers / exposure | Responsibility | Validity | Canonical owner | Disposition |
| --- | --- | --- | --- | --- | --- |
| `qpx_harness/bundle.py` | Legacy CLI route `bundle`; no registry exposure; no direct code-search consumer found | Local performance profiling bundle tooling | Stale: attempts to copy removed root modules `runtime.py`, `evidence.py`, and `profiling.py` | Historical/retired legacy CLI tooling | `DELETE_AFTER_CALLER_MIGRATION` |
| `qpx_harness/evidence_diagnose_smoke.py` | No canonical CLI/registry exposure; no direct code-search consumer found | Integration verification of Evidence -> Analysis -> Diagnose composition | Valid integration smoke, but not a production capability owner | `qpx_harness.validation` | `MOVE_TO_VALIDATION` |
| `qpx_harness/scale_audit.py` | Legacy CLI route `scale-audit`; pytest self-test aggregation | Quantitative QVT multiphysics scale derivation and classification | Live and valid; functionality is analytical rather than root/package plumbing | `qpx_harness.analysis` | `MOVE_TO_CAPABILITY` |

## Migration

The resulting ownership is:

```text
qpx_harness/analysis/scale_audit.py
qpx_harness/validation/evidence_diagnose_smoke.py
```

The stale `bundle` command and root implementation are retired rather than reviving the removed root-module layout.

The `scale-audit` command remains available, but routes to `qpx_harness.analysis.scale_audit:main`.

`qpx_harness/__init__.py` now exposes current canonical packages instead of stale root symbols such as `bundle`, `preflight`, `profiling`, `regression`, and `temporal`.

## Architectural closure rule

After migration, the only Python file allowed directly at the `qpx_harness/` package root is `__init__.py`.

`tools/qpx_architecture_census.py` therefore treats every new direct `qpx_harness/*.py` module other than `__init__.py` as an unowned root surface and fails the architecture census. Long-lived behavior must be placed under a canonical capability package.

## Scientific semantics

No physics equations, constants, thresholds, case definitions, validation criteria, or experiment sequencing were changed. `scale_audit.py` and `evidence_diagnose_smoke.py` were moved without changing their implementation bodies. The `bundle` surface was already structurally stale and was removed as legacy compatibility tooling.
