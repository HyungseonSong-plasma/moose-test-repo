# Root-level qpx_harness surface refactor plan

## Objective

Reduce transitional and one-off modules at the `qpx_harness/` package root so production ownership is expressed through stable capability packages rather than historical root-level entrypoints.

## Initial signals

- `qpx_harness/bundle.py` is a standalone profiling-bundle builder that still assumes removed root modules such as `runtime.py`, `evidence.py`, and `profiling.py`.
- `qpx_harness/evidence_diagnose_smoke.py` is an integration smoke over canonical `application`, `evidence`, and `diagnose` packages and is better owned by validation/test infrastructure than the production package root.
- Similar root-level modules must be censused before any deletion or move.

## Refactor rule

For every root-level production module, classify exactly one disposition:

- MOVE_TO_CAPABILITY
- MOVE_TO_VALIDATION
- MOVE_TO_TOOLING
- MOVE_TO_EXPERIMENT_OR_RECIPE
- DELETE_AFTER_CALLER_MIGRATION
- RETAIN_WITH_JUSTIFICATION

Do not rename or move solely for aesthetics. Preserve user-facing behavior and scientific semantics.

## Batches

### A. Root surface census

Enumerate every direct child module under `qpx_harness/` that is not a stable capability package. Record callers, CLI exposure, tests, responsibility, and current validity.

### B. Broken/stale root entrypoints

Start with `bundle.py` and any peer modules that reference removed package layout. Either migrate them to the current canonical owner or retire them if no live caller exists.

### C. Validation/smoke relocation

Move integration-only smoke/characterization code such as `evidence_diagnose_smoke.py` out of production root ownership and into validation/tests/tooling as appropriate.

### D. CLI/import cleanup

Update remaining CLI imports, package exports, tests, and docs to use canonical owners directly. Remove compatibility aliases that only exist to preserve old root paths.

### E. Architecture guard

Extend the architecture census so new generic root-level modules require explicit classification/justification instead of silently accumulating at `qpx_harness/*.py`.

## Validation

- `python tools/qpx_dependency_guard.py --check all`
- `python tools/qpx_architecture_census.py`
- `python tools/qpx_experiment_gateway_guard.py`
- `python -m pytest -q`
- `python qpx -i all`

No scientific EVR/P3 unless execution semantics are changed rather than import/ownership routing only.
