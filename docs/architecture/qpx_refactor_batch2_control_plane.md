# QPX refactor Batch 2 — canonical experiment control plane

Status: implementation evidence for #147 C2-C5.

## Completed changes

- Canonical experiment entrypoints are `qpx compile`, `qpx plan`, `qpx lower`, and `qpx run` over schema-v2 `qpx_harness.specification.ExperimentSpec`.
- `qpx run` no longer reads schema-v1 payloads or falls back to campaign protocol runners.
- `qpx -e/--experiment` is retired and reports the schema-v2 migration route.
- `qpx_harness.application` no longer exports schema-v1 `ExperimentControl`, `run_experiment`, or protocol-registry APIs.
- Production schema-v1 ownership was physically removed:
  - `qpx_harness/application/experiment_spec.py`
  - `qpx_harness/application/experiment_registry.py`
  - `qpx_harness/application/experiment_service.py`
  - `qpx_harness/application/protocols/`
- Historical schema-v1 `experiments/**/experiment.json` files may remain as provenance fixtures, but the canonical application/CLI does not execute them.
- `tools/qpx_experiment_gateway_guard.py` now enforces one production schema/control plane and zero protocol dispatch.

## Execution boundary

`qpx run` compiles and lowers the complete semantic pipeline, then returns BLOCKED until a generic target executor is approved. It must not use an Issue/R3/R4 runner as an execution fallback.

This preserves the distinction between architecture readiness and scientific/runtime validation.

## Batch-2 acceptance intent

```text
CANONICAL_EXPERIMENT_SCHEMA_COUNT = 1
PARALLEL_EXPERIMENT_CONTROL_PLANES = 0
PROTOCOL_STRING_CAMPAIGN_DISPATCH = 0
PRODUCTION_CAMPAIGN_PROTOCOL_MODULES = 0
DECLARATIVE_EXPERIMENT_GATEWAY = PASS
EXPERIMENT_CONTROL_PLANE_GUARD = PASS
```

The repository CI result for this commit is the regression evidence for C5. If CI identifies stale imports in tests or validation code, they must be migrated as part of this same batch before #147 is closed.
