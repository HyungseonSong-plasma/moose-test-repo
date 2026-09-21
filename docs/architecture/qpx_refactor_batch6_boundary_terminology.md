# Batch 6 final ownership manifest — model terminology and MOOSE boundary

Status: canonical post-migration architecture for #150 T2-T6 and #146 M1-M6.

This manifest records ownership after the Batch 6 migration. It does not assert scientific validation and does not change numerical or plasma-physics behavior.

## Canonical selected-model terminology

The selected simulation/model value is an opaque upstream reference, not a registry-resolved identifier or runtime object. The one canonical field name is:

```text
model_ref
```

It is propagated without semantic aliases through:

```text
ExperimentSpec
  -> ExperimentIntent
  -> ScientificPolicy
  -> ExecutionPlan
  -> MooseCaseIR / MooseTargetIR
```

The following generic ownership names are retired:

- `qpx_harness/ontology/model.py` -> semantic records are owned by `qpx_harness/ontology/records.py`;
- top-level `qpx_harness/models/` -> evaluation/statistics contracts are owned by `qpx_harness/evaluation/statistics.py`;
- `qpx_harness/adapters/moose/mutation_spec/models.py` -> mutation-spec records are owned by `mutation_spec/schema.py` and `mutation_spec/plan.py`.

External/framework names such as Pydantic `model_validate` / `model_dump`, legitimate mathematical/physical uses of “model”, and immutable provenance text remain valid.

## Single MOOSE integration boundary

The one public MOOSE integration boundary is:

```text
qpx_harness/adapters/moose/
```

The peer `qpx_harness/moose/` production root is retired.

### Ownership graph

| Responsibility | Canonical owner |
|---|---|
| semantic `ExecutionPlan` -> MOOSE target IR | `qpx_harness/adapters/moose/target.py` |
| HIT/MOOSE parsing and input structure | `qpx_harness/adapters/moose/input.py` |
| block and parameter input mechanics | `qpx_harness/adapters/moose/blocks.py`, `parameters.py` |
| mutation specification | `qpx_harness/adapters/moose/mutation_spec/` |
| mutation application / transform realization | `qpx_harness/adapters/moose/transforms.py` |
| execution/preflight/check-input mechanics | `qpx_harness/adapters/moose/preflight.py` and solver-boundary runtime helpers |
| MOOSE/QPX log and nonlinear runtime decoding | `qpx_harness/adapters/moose/log.py`, `nonlinear_solver.py` |
| MOOSE output configuration/decoding | `qpx_harness/adapters/moose/output_observation.py` |
| MOOSE-coupled PETSc option mutation | `qpx_harness/adapters/moose/petsc_options.py` |
| normalized solver-independent evidence | `qpx_harness/evidence/` after boundary decoding |
| scientific analysis/reasoning/acceptance | generic `analysis`, `reasoning`, `validation` owners |

## Allowed dependency direction

```text
specification / ontology / planning
        -> execution plan
        -> adapters/moose
        -> decoded observations/evidence
        -> analysis/reasoning/validation
```

Generic semantic, evidence, analysis, and reasoning layers must not import concrete MOOSE parser, mutation, runtime, or log-decoder implementations. Presentation may invoke an explicit solver-boundary operation where the command itself is explicitly MOOSE-facing (for example preflight), but this is not generic semantic ownership.

Historical experiment/characterization code may explicitly call a canonical solver-boundary decoder when it intentionally consumes raw MOOSE/PETSc artifacts; it must not obtain such decoders through the generic evidence API.

## External-contract exemptions

The following classes of names remain intentionally MOOSE/PETSc/QPX-specific behind the boundary:

- exact MOOSE block/object/type/property and parameter spellings;
- HIT/MOOSE input grammar and executioner syntax;
- PETSc option strings used inside MOOSE inputs;
- PETSc diagnostic output grammar and exact command-line options;
- QPX/MOOSE telemetry, object names, and required external identifiers;
- exact Green–Gauss or Jacobian external diagnostic identifiers where they denote the real external method/contract.

These names are not architectural leakage when owned by `adapters/moose` or the explicit backend diagnostic owner and normalized before generic consumers use them.

## Guarded acceptance contract

`tools/qpx_boundary_terminology_guard.py` enforces the Batch 6 structural acceptance, including:

```text
CANONICAL_SELECTED_MODEL_TERM = model_ref
CANONICAL_SELECTED_MODEL_TERM_COUNT = 1
AMBIGUOUS_MODEL_FIELDS_IN_CONTROL_PLANE = 0
TOP_LEVEL_GENERIC_MODELS_PACKAGE = 0
ONTOLOGY_RECORD_MODULES_NAMED_GENERIC_MODEL = 0
MUTATION_SCHEMA_MODULES_NAMED_GENERIC_MODELS = 0
PUBLIC_MOOSE_INTEGRATION_BOUNDARY_COUNT = 1
PARALLEL_MOOSE_ROOTS = 0
MOOSE_INPUT_REALIZATION_OWNER_COUNT = 1
MOOSE_SYNTAX_MUTATION_OWNER_COUNT = 1
MOOSE_OUTPUT_DECODER_OWNER_COUNT = 1
GENERIC_TO_MOOSE_CONCRETE_DEPENDENCY_EDGES = 0
GENERIC_EVIDENCE_TO_CONCRETE_SOLVER_LOG_DECODING_EDGES = 0
MODEL_TERMINOLOGY_GUARD = PASS
MOOSE_ADAPTER_BOUNDARY_GUARD = PASS
```

Batch 6 is complete only when the clean development HEAD, with no migration shim, passes this guard plus dependency/cycle guards, strict architecture census, QPX-free pytest, canonical internal validation, and retained science-characterization guards.
