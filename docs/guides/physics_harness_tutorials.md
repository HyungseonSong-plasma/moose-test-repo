# Physics Harness Tutorial Series

**Status:** current operator guidance  
**Canonical control plane:** schema-v2 `ExperimentSpec`  
**Stable CLI entrypoint:** `python3 bin/physics.py`

This guide describes the architecture implemented after the #280 gateway cutover. Historical Issue/campaign documents may preserve earlier QPX names, schema-v1 protocol strings, local MOOSE lowering, and retired command spellings as evidence. Those historical records are not execution instructions.

## 1. Current command surface

The supported semantic command family is:

```bash
python3 bin/physics.py compile experiments/semantic/electron_energy_diffusion/experiment.json
python3 bin/physics.py plan experiments/semantic/electron_energy_diffusion/experiment.json
python3 bin/physics.py run experiments/semantic/electron_energy_diffusion/experiment.json
```

The commands mean:

```text
compile -> validate schema-v2 intent and produce ExperimentIntent
plan    -> synthesize ScientificPolicy and solver-independent ExecutionPlan
run     -> prepare Physics semantics for the explicit canonical SOL request/runtime boundary
```

`lower` is retained only as a fail-closed retirement marker. It no longer lowers an `ExecutionPlan` into local MOOSE target IR. Canonical SOL execution requires an explicit reviewed `CanonicalRealizationModel`, Physics-to-SOL capability mapping, backend target, pinned runtime consumer, and adapter path. Physics must not infer these from `ExecutionPlan` spelling, tuple order, or local solver objects.

The current CLI `run` performs Physics planning and then stops with `SOL_REQUEST: BLOCKED` because those reviewed runtime inputs are not accepted as CLI arguments yet. This is deliberate: there is no local MOOSE fallback.

Repository/harness regression validation remains available through the compatibility/internal route:

```bash
python3 bin/physics.py -i regression
```

The former documented `architecture` and `all` aliases are retired rather than silently mapped to a different lifecycle. Internal validation is not scientific acceptance by itself.

## 2. Schema-v2 experiment model

The canonical experiment schema is version 2. A representative current experiment is:

```text
experiments/semantic/electron_energy_diffusion/experiment.json
```

Its semantic fields include `schema_version`, `experiment_id`, `description`, `objective`, `target_claims`, `requested_capabilities`, `parameters`, `constraints`, `observations`, `execution_bounds`, `cases`, `provenance`, and `model_ref`.

A canonical schema-v2 experiment does **not** select a campaign runner with a `protocol` string. Scientific intent is compiled into reusable capability/policy/planning objects. A separate reviewed canonical realization model is then compiled into a SOL Public Contract request and handed to the pinned upstream runtime consumer.

## 3. Historical schema-v1 fixtures

Schema-v1 `experiments/**/experiment.json` files that contain fields such as `protocol`, `execution`, and `outputs` are retained only when useful as immutable provenance or characterization fixtures. They are not part of the canonical application API and must not be submitted through a retired protocol-dispatch gateway.

Allowed uses include characterization tests, provenance reconstruction, comparison against a migrated semantic implementation, and evidence needed to explain an earlier scientific decision. A historical fixture is not automatically a current/re-runnable experiment simply because it is stored under `experiments/`.

## 4. Runtime and scientific acceptance

The canonical ownership chain is:

```text
schema-v2 Physics intent
  -> ScientificPolicy
  -> solver-independent ExecutionPlan
  -> reviewed CanonicalRealizationModel + capability mapping
  -> SolRequest
  -> pinned SOL runtime consumer
  -> sol-adapter-moose
  -> runtime/protocol evidence
  -> separate scientific interpretation / V&V
```

Runtime/protocol completion is not a scientific PASS. Closure-grade scientific claims still require their governed numerical/physical acceptance gates and provenance.

## 5. Designing a new experiment

For a new canonical semantic experiment:

1. start with the scientific claim and required evidence;
2. express reusable intent in schema-v2 rather than Issue/protocol identity;
3. use `compile` and `plan` to inspect the Physics semantic chain;
4. define canonical realization semantics explicitly; do not encode MOOSE-native object spelling in Physics semantics;
5. compile the reviewed realization and capability mapping into `SolRequest`;
6. invoke the pinned SOL runtime consumer and adapter boundary;
7. evaluate physical/numerical acceptance separately from protocol/runtime success;
8. keep thresholds and acceptance logic in their semantic owner, not generic CLI/runtime code.

## 6. Failure-layer discipline

Classify failures at the layer where they occur:

```text
schema / semantic compilation
planning / policy
canonical realization / SOL request compilation
runtime selection / protocol validation
adapter realization / execution
observation / evidence
scientific acceptance
```

A construction failure is not a physics failure, and a completed runtime is not automatically a scientific PASS.

## 7. Quick reference

```bash
# Canonical Physics semantic surface
python3 bin/physics.py compile <schema-v2-experiment.json>
python3 bin/physics.py plan <schema-v2-experiment.json>
python3 bin/physics.py run <schema-v2-experiment.json>

# Explicit retirement marker: returns non-zero, never performs local MOOSE lowering
python3 bin/physics.py lower <schema-v2-experiment.json>

# Compatibility/internal repository validation
python3 bin/physics.py -i regression
```

The durable rule is: **Physics owns scientific semantics and request compilation; simulation-ontology owns generic SOL runtime mechanics; sol-adapter-moose owns MOOSE-native realization/execution; runtime completion and scientific V&V remain distinct claims.**
