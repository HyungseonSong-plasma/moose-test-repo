# Physics Harness Tutorial Series

**Status:** current operator guidance  
**Canonical control plane:** schema-v2 `ExperimentSpec`  
**Stable CLI entrypoint:** `python3 bin/physics.py`

This guide describes the architecture currently implemented on `main`. Historical Issue/campaign documents may preserve earlier QPX names, schema-v1 protocol strings, and retired command spellings as evidence. Those historical records are not execution instructions.

## 1. Current command surface

The supported semantic command family is:

```bash
python3 bin/physics.py compile experiments/semantic/electron_energy_diffusion/experiment.json
python3 bin/physics.py plan experiments/semantic/electron_energy_diffusion/experiment.json
python3 bin/physics.py lower experiments/semantic/electron_energy_diffusion/experiment.json
python3 bin/physics.py run experiments/semantic/electron_energy_diffusion/experiment.json
```

The commands mean:

```text
compile -> validate schema-v2 intent and produce ExperimentIntent
plan    -> synthesize ScientificPolicy and solver-independent ExecutionPlan
lower   -> lower the plan to MOOSE target IR
run     -> prepare the canonical semantic target-execution surface
```

`run` currently **does not execute the target solver**. It prepares the semantic target IR and terminates with `TARGET_EXECUTION: BLOCKED` until a generic target executor is explicitly approved. Falling back to a historical protocol/campaign runner is forbidden.

Repository/harness internal validation is still available through the compatibility/internal route:

```bash
python3 bin/physics.py -i architecture
python3 bin/physics.py -i regression
python3 bin/physics.py -i all
```

Internal validation is not scientific acceptance by itself.

## 2. Schema-v2 experiment model

The canonical experiment schema is version 2. A representative current experiment is:

```text
experiments/semantic/electron_energy_diffusion/experiment.json
```

Its semantic fields include:

```text
schema_version
experiment_id
description
objective
target_claims
requested_capabilities
parameters
constraints
observations
execution_bounds
cases
provenance
model_ref
```

A canonical schema-v2 experiment does **not** select a campaign runner with a `protocol` string. Scientific intent is compiled into reusable capability/policy/planning objects and only then lowered through the solver adapter boundary.

## 3. Historical schema-v1 fixtures

Schema-v1 `experiments/**/experiment.json` files that contain fields such as `protocol`, `execution`, and `outputs` are retained only when they are useful as immutable provenance or characterization fixtures.

They are not part of the canonical application API and must not be submitted through a retired protocol-dispatch gateway. Their allowed uses are narrowly historical, for example:

- characterization tests that freeze an accepted historical parameter set;
- provenance reconstruction;
- comparison against a migrated semantic implementation;
- evidence needed to explain an earlier scientific decision.

A historical fixture is not automatically a current/re-runnable experiment simply because it is stored under `experiments/`.

## 4. Scientific runtime acceptance

Until the generic schema-v2 target executor is approved, closure-grade scientific runtime is owned by an explicit governed acceptance surface. The normal pattern is:

```text
accepted scientific claim
  -> dedicated bounded runner
  -> P0 self-test / mutation controls
  -> P1 static/numerical preflight
  -> P2 real physics-opt --check-input
  -> P3 exact-head real physics-opt runtime
  -> evidence/analyzer
  -> explicit PASS / FAIL / HOLD
  -> provenance-controlled CI artifact
```

A successful process return is not enough. The acceptance runner must own the scientific gates required by the issue.

### Current Stage-6 example

Issue #193 is the current A8 finite-SEE particle acceptance owner. The historical A8 schema-v1 fixture under `experiments/Issue27_surface_reactions/A8_finite_see/` remains useful for characterization, while current acceptance must be established through the governed #193 exact-head `physics-opt` surface. The historical fixture must not be promoted back into an executable protocol-dispatch control plane.

## 5. Designing a new experiment

For a new canonical semantic experiment:

1. start with the scientific claim and required evidence;
2. express reusable intent in schema-v2 rather than Issue/protocol identity;
3. use `compile`, `plan`, and `lower` to inspect the semantic chain;
4. use `run` only for the currently supported preparation boundary;
5. if scientific P3 is required, provide or reuse a governed acceptance runner/workflow rather than reviving historical dispatch;
6. keep thresholds and acceptance logic in their semantic owner, not in generic CLI code.

A useful mental model is:

```text
schema-v2 experiment intent
  -> semantic compilation
  -> scientific policy
  -> execution plan
  -> solver target IR
  -> approved governed executor
  -> evidence
  -> scientific decision
```

## 6. Failure-layer discipline

Classify failures at the layer where they occur:

```text
schema / semantic compilation
planning / policy
lowering / target construction
P1/P2 construction or environment
P3 runtime / convergence
observation / evidence
scientific acceptance
```

A construction failure is not a physics failure, and a converged runtime is not automatically a scientific PASS.

## 7. Quick reference

```bash
# Canonical semantic pipeline
python3 bin/physics.py compile <schema-v2-experiment.json>
python3 bin/physics.py plan <schema-v2-experiment.json>
python3 bin/physics.py lower <schema-v2-experiment.json>
python3 bin/physics.py run <schema-v2-experiment.json>

# Compatibility/internal repository validation
python3 bin/physics.py -i all
```

The durable rule is simple: **schema-v2 owns current semantic intent; historical schema-v1 fixtures own provenance only; closure-grade runtime must use an approved governed execution surface.**
