# QPX refactor foundation manifest

Status: canonical architecture decision for #145 Batch 1 (#150 T0-T1, #146 M0, #147 C0-C1).

This document fixes the vocabulary and ownership decisions that downstream refactors must follow. It does not move solver code or change scientific/numerical behavior.

## 1. Selected simulation-model reference (#150 T0-T1)

### Census

The token `model` currently has at least four independent meanings in canonical production:

1. **Selected simulation-model reference**: `ExperimentSpec.model`, propagated through `ExperimentIntent`, `ScientificPolicy`, `ExecutionPlan`, `MooseCaseIR`, and `MooseTargetIR`.
2. **Ontology record module**: `qpx_harness/ontology/model.py`, which owns solver-independent semantic records.
3. **Evaluation/statistics data contracts**: top-level `qpx_harness/models/`.
4. **MOOSE mutation schema records**: `qpx_harness/adapters/moose/mutation_spec/models.py`.

External framework methods such as Pydantic `model_validate`/`model_dump`, mathematical/ML model terminology, and exact external contract names are exempt from the canonical selected-model rename.

### Selected-model semantics

The selected value is an **opaque reference supplied by experiment intent**. The current pipeline does not resolve it through a model registry, prove that it is a stable database identifier, or attach object behavior to it. It is copied unchanged across semantic and solver-target layers.

Therefore the canonical term is:

```text
model_ref
```

`simulation_model_id` is intentionally rejected because the current contract does not establish ID semantics. `model_ref` states only what the architecture can prove: this value references the simulation/model choice selected upstream.

Batch 6 (#150 T2-T6) must propagate `model_ref` end-to-end and separately rename generic record/schema owners according to their actual responsibilities. No compatibility alias is to remain indefinitely.

## 2. MOOSE ownership census and dependency map (#146 M0)

### Current concrete roots

Two peer MOOSE-facing roots exist today:

- `qpx_harness/moose/`
  - `input.py`: HIT/MOOSE parse structure
  - `blocks.py`, `parameters.py`: text/input mutation
  - `check_input.py`, `executioner.py`, `preflight.py`: execution-facing/preflight mechanics
  - `dofmap.py`, `log.py`: MOOSE/QPX runtime/output decoding support
  - `output_observation.py`: MOOSE output configuration plus observation-related behavior
- `qpx_harness/adapters/moose/`
  - `target.py`: semantic `ExecutionPlan` -> structured MOOSE target IR and rendering
  - `mutation_spec/`: declarative MOOSE mutation schema
  - `dmix_equivalence.py`: campaign-specific MOOSE realization (semantic cleanup owned by #148)
  - `electron_inventory/`: species/campaign-specific MOOSE realization (semantic cleanup owned by #148)

### Canonical destination

The single public integration boundary is:

```text
qpx_harness/adapters/moose/
```

The later #146 migration may introduce internal subpackages (`syntax`, `mutation`, `runtime`, `observation`) but must not retain `qpx_harness/moose/` as a peer public boundary.

### Ownership classes

| Responsibility | Canonical owner after migration |
|---|---|
| semantic plan -> MOOSE target IR | `adapters/moose` lowering |
| HIT/MOOSE parser and deterministic rendering | `adapters/moose` syntax/input backend |
| block/parameter mutation application | `adapters/moose` mutation backend |
| check-input, executioner, preflight, solver invocation support | `adapters/moose` runtime backend |
| MOOSE/QPX log/output decoding | `adapters/moose` observation/decoder backend |
| normalized evidence/observations | generic evidence/observation packages, after decoding |
| scientific acceptance/reasoning | generic reasoning/validation, never MOOSE backend |

### Known boundary bypasses

`qpx_harness/transforms/registry.py` directly consumes concrete `qpx_harness.moose` parser/mutation mechanics while also consuming adapter mutation specifications. This is a forbidden generic-to-concrete solver dependency and must be removed in #146 M4.

Generic evidence that directly parses concrete MOOSE/PETSc logs is likewise a boundary violation; decoding belongs behind the solver/external-diagnostic boundary and normalized evidence belongs above it.

## 3. Experiment-control census and canonical schema decision (#147 C0-C1)

### Current control planes

**Canonical semantic plane (schema v2)**

```text
qpx_harness.specification.ExperimentSpec
 -> compile_experiment_intent
 -> ScientificPolicy
 -> ExecutionPlan
 -> target adapter
```

This plane describes objective, capabilities, parameters, constraints, observations, cases, execution bounds, provenance, and selected `model_ref` semantics without target mutation syntax.

**Legacy compatibility plane (schema v1)**

```text
qpx_harness.application.experiment_spec.ExperimentControl
 -> protocol string
 -> qpx_harness.application.experiment_registry
 -> campaign-named protocol runner
```

The registry currently maps Issue26, Issue27, R3, and R4 protocol identifiers to production runner modules. This is compatibility/campaign dispatch, not the canonical architecture.

### Decision

`qpx_harness.specification.ExperimentSpec` schema v2 is the **only canonical experiment schema**.

Schema v1 `ExperimentControl` is frozen compatibility input and must not gain capabilities, new protocols, or new canonical callers.

### Translation/retirement policy

1. New experiments must be authored as schema v2.
2. No new production protocol-string runners may be added.
3. A legacy v1 fixture may be translated to v2 only when its scientific intent, parameters, constraints, observations, execution bounds, and cases can be represented without embedding solver mutation syntax or campaign dispatch into v2.
4. Translation must be explicit and deterministic. Fields without a valid semantic mapping remain historical replay/provenance rather than being guessed into v2.
5. A legacy runner is removed only after its reusable capabilities are reachable through the v2 semantic planning path; immutable historical fixtures may remain under experiment/provenance ownership.
6. Canonical CLI/application commands must converge on the v2 compile/plan/lower/run gateway. Dedicated campaign commands are compatibility surfaces pending retirement, not alternative control planes.

## 4. Dependency invariant for subsequent batches

```text
ExperimentSpec(v2)
  -> semantic records / planning
  -> ExecutionPlan
  -> adapters/moose (one external-solver boundary)
  -> decoded generic observation/evidence
  -> generic analysis/reasoning/validation
```

Forbidden directions include:

- generic semantic/planning code -> MOOSE/PETSc syntax/runtime modules;
- generic evidence -> raw MOOSE/PETSc parser implementation;
- experiment schema -> Issue/PF/R3/R4 campaign runner selection;
- solver adapter -> scientific acceptance policy;
- new canonical field aliases for the selected model reference.

## 5. Batch-1 completion contract

This manifest completes the **decision/census** scope only:

```text
#150 T0 MODEL_TERM_CENSUS = COMPLETE
#150 T1 SELECTED_MODEL_SEMANTICS = model_ref
#146 M0 MOOSE_OWNERSHIP_CENSUS = COMPLETE
#146 M0 CANONICAL_MOOSE_DESTINATION = qpx_harness/adapters/moose
#147 C0 CONTROL_PLANE_CENSUS = COMPLETE
#147 C1 CANONICAL_SCHEMA = ExperimentSpec schema v2
#147 C1 LEGACY_V1_POLICY = FROZEN_COMPATIBILITY_THEN_RETIRE
```

Physical renames, protocol retirement, package moves, and dependency rewrites belong to later batches and are deliberately not performed here.