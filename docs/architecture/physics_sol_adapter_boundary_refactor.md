# Physics -> SOL Adapter Boundary Refactor

**Status:** RFC / CodeRabbit review candidate  
**Issue:** #274  
**Parent:** #157  
**Scientific EVR:** 0  
**Review baseline:**

```text
moose-test-repo main      = 057acd7e810bc8219fa855b8f59fc676013503ea
simulation-ontology main  = a2fefa213825dc58e03e03ab468ad1989dc39d6b
sol-adapter-moose main    = f35563f0e63e2739cb94a36c450d5d66024aff2a
```

## 1. Decision summary

The long-range cut is not:

```text
Physics -> new Python AdapterRuntime -> MOOSE
```

and it is not:

```text
Physics ExecutionPlan == SOL MappingPlan
```

The target is:

```text
Physics research / experiment semantics
        |
        | explicit canonical-model / realization handoff
        v
SOL Public Contract 0.2 request
  BackendTarget + MappingPlan + RealizationSpec
        |
        v
existing simulation-ontology sol-adapter-runtime
        |
        v
Adapter Protocol 0.2
        |
        v
sol-adapter-moose
        |
        v
adapter-local MOOSE IR / input / runtime / backend evidence
```

The existing SOL runtime is reused. No second registry, JSON-RPC transport, process/session lifecycle, compatibility evaluator, adapter selector, or response-loss policy is created in `moose-test-repo`.

The current direct semantic edge

```text
physics_harness/application/gateway.py
  -> physics_harness.adapters.moose
  -> MooseTargetIR / lower_execution_plan
```

is transitional debt. This RFC freezes it as the only direct MOOSE dependency in the canonical semantic control-plane surface while the cross-repository contract is made executable.

## 2. Why a direct ExecutionPlan -> RealizationSpec converter is unsafe

The current Physics `ExecutionPlan` is a research-execution IR compiled from `ScientificPolicy`. SOL `MappingPlan + RealizationSpec` is a public semantic realization contract. They have different information content and different ownership.

A direct structural rename or field-copy would silently invent semantics.

The current Physics plan does not contain all information required by Public Contract 0.2:

- canonical entity graph;
- canonical semantic types;
- spatial scopes;
- semantic relations;
- unit-bearing quantities;
- explicit MappingPlan action dependency graph;
- action bindings to entities, relations, and scopes;
- canonical SOL backend capability names.

Therefore:

```text
EXECUTION_PLAN_EQ_MAPPING_PLAN = false
EXECUTION_CASE_EQ_MAPPING_ACTION = false
RAW_PARAMETER_EQ_SOL_QUANTITY = false
MODEL_REF_EQ_SOL_SOURCE_MODEL = not established
PHYSICS_CAPABILITY_ID_EQ_SOL_BACKEND_CAPABILITY = false unless explicitly mapped
```

## 3. Responsibility model

### 3.1 Keep in Physics

The Physics harness owns research/development semantics:

- experiment objective;
- claims and open questions;
- hypotheses and assessments;
- evidence and diagnostic conclusions;
- development state;
- scientific search policy;
- selected interventions;
- held-fixed scientific constraints;
- experiment acceptance requirements;
- experiment-level execution intent;
- Physics-specific evidence interpretation.

These concepts answer **why the experiment is being run and how evidence changes the development state**. They are not backend realization objects.

### 3.2 Canonicalize through SOL

The SOL model/public contract owns simulation-model realization meaning:

- canonical model identity;
- mathematical/physics/constitutive entities;
- fields;
- material/physical quantities with units;
- boundary/condition entities;
- analysis entities;
- observations as semantic model entities;
- scopes;
- semantic relations;
- backend target;
- adapter-facing required capabilities;
- MappingPlan action/dependency structure;
- action bindings into the realization graph.

These concepts answer **what simulation meaning is to be realized by an adapter**.

### 3.3 Keep in simulation-ontology runtime

The existing `sol-adapter-runtime` owns:

- explicit adapter registration;
- subprocess/session lifecycle;
- mandatory `describe_adapter` bootstrap;
- live Adapter Protocol compatibility;
- live Public Contract compatibility;
- capability discovery;
- solver-neutral candidate projection;
- deterministic selection;
- `validate_plan_v02`;
- `execute_plan_v02`;
- response-loss / no-replay semantics.

Static Physics configuration must not become compatibility authority.

### 3.4 Keep in sol-adapter-moose

The external MOOSE adapter owns:

- MOOSE object selection;
- local MOOSE naming;
- typed MOOSE IR;
- MOOSE input serialization;
- `--check-input`;
- configured MOOSE/Physics execution;
- MOOSE/PETSc-facing output decoding;
- backend-specific provenance;
- backend numerical/physical V&V.

MOOSE-native object identity must not leak upstream into canonical Physics research semantics or SOL public semantics.

## 4. Current direct MOOSE edges: classification

Not every MOOSE reference in `physics_harness` is the same defect.

### Semantic control-plane debt

```text
physics_harness/application/gateway.py
  -> physics_harness.adapters.moose
```

This is the direct edge owned by #274.

### Explicit target-specific operational surfaces

Current explicit MOOSE-specific routes such as:

```text
physics_harness/cli/app.py
  -> physics_harness.adapters.moose.preflight

physics_harness/application/performance.py
  -> physics_harness.adapters.moose.performance.*
```

are not evidence that the semantic `ExperimentSpec -> ExecutionPlan` pipeline should know MOOSE. They are separately classified target-specific operational utilities.

Their eventual extraction/retirement belongs to later MOOSE_GENERIC migration work. #274 must not hide them, but it also must not conflate them with the semantic cut line.

## 5. ExecutionPlan -> SOL ownership matrix

| Physics field | Current meaning | SOL disposition | Rule |
|---|---|---|---|
| `plan_id` | local deterministic plan identity | local trace/provenance | must not become canonical SOL semantic identity by convenience |
| `source_policy_id` | local ScientificPolicy lineage | local provenance | not a MappingPlan semantic field |
| `cases` | research execution cases | no direct 1:1 mapping | one case may require multiple MappingPlan actions |
| `case_id` | Physics case identity | local trace unless explicitly bound | never infer physics from spelling |
| `action_id` | selected Physics ActionSpec identity | possible opaque lineage/binding input | action spelling is not realization semantics |
| `target` | Physics policy target category | projection input only | not a backend target and not a SOL semantic type |
| `intervention_type` | Physics research intervention taxonomy | Physics-local policy | must not become MOOSE/SOL operator spelling |
| `parameters` | untyped Python values | blocked from direct SOL quantity use | requires semantic parameter identity + unit |
| `required_observations` | requested Physics observations | derive SOL observation entities where supported | requires canonical semantic owner |
| `held_fixed` | experiment preservation constraints | primarily Physics policy | serialize only if a canonical SOL contract owns the meaning |
| `model_ref` | opaque selected-model string | candidate source-model reference | only after canonical SOL identity/artifact contract is established |
| `execution_bounds` | dt/end-time/step constraints | unresolved split | classify as analysis semantics vs runtime policy before serialization |
| `artifact_contracts` | Physics evidence expectations | Physics/evidence layer | not adapter realization semantics by default |
| `target_capabilities` | Physics capability IDs | explicit mapping required | do not reuse as Adapter Protocol capabilities implicitly |
| `derived_values` | policy-derived values | no direct generic mapping | only typed/unit-owned semantic values may cross |
| `provenance_id` | Physics provenance lineage | local/cross-system trace | must not redefine SOL identity |

## 6. Information gaps that block production cutover

### G1 — canonical source model identity

Current example:

```json
"model_ref": "oxygen_icp_electron_energy"
```

is an opaque local string. Before it can become `RealizationSpec.source_model`, the system needs a contract establishing:

- canonical SOL model identity;
- immutable or versioned model artifact identity;
- model schema/public-contract version;
- model provenance;
- resolution behavior when the model is unavailable.

### G2 — unit-bearing parameter ownership

Physics `ActionSpec.parameters` currently contains values such as:

```text
diffusivity = 100.0
```

SOL RealizationSpec requires semantic quantity identity and unit, not an untyped scalar. A canonical parameter registry/model must establish, for example, the semantic parameter and unit before crossing the public boundary.

No code may guess units from variable names.

### G3 — entity / relation / scope graph

The local research plan does not encode the complete simulation-model graph required by RealizationSpec. That graph must come from canonical model semantics, not be reconstructed from MOOSE spellings or action-name strings.

### G4 — MappingPlan dependency graph

Physics `ExecutionPlan.cases` is ordered but does not define the explicit dependency graph required by MappingPlan. A later compiler must establish dependencies from canonical realization/planning semantics.

Tuple order is not dependency meaning.

### G5 — capability vocabulary

Current Physics capabilities such as `electron_energy_diffusion` are research/scientific capability IDs. Adapter Protocol capabilities such as `thermal.steady_conduction` are backend-facing declared capabilities.

A reviewed mapping/compilation step is required. String reuse is not a contract.

### G6 — stable runtime consumer entrypoint

`simulation-ontology` already contains the correct Rust runtime implementation but its normal `sol-cli` does not currently expose the full external runtime v0.2 flow as a stable consumer command.

The preferred fix is upstream:

```text
stable simulation-ontology runtime CLI/API
  -> sol-adapter-runtime
  -> external adapter
```

not a Python reimplementation of SOL transport/runtime semantics in Physics.

## 7. Cross-repository boundary rule

The migration must choose one of these acceptable shapes:

### Preferred

Physics produces/identifies canonical SOL model + experiment realization intent, then invokes a stable upstream SOL consumer that builds/validates the Public Contract 0.2 request and uses `sol-adapter-runtime`.

### Acceptable only if SOL publishes it as a supported public boundary

Physics serializes a SOL-defined Public Contract payload using pinned canonical schemas/tooling and hands it to a stable upstream runtime entrypoint.

### Rejected

```text
Physics custom adapter envelope
Physics-local clone of RealizationSpec DTOs with independent semantics
Physics-local AdapterRegistry
Physics-local JSON-RPC framing/session implementation
Physics interpreting sol-adapter-moose process responses directly
Physics ExecutionPlan renamed to MappingPlan
action-id spelling used to infer physics
MOOSE input/object names used to synthesize SOL semantics
```

## 8. CLI lifecycle

Current canonical-looking commands:

```text
physics compile
physics plan
physics lower
physics run
```

need different long-range dispositions.

### Keep

`compile` and `plan` remain valid Physics research/semantic operations.

### Transitional

`lower` currently means local MOOSE lowering even though it sits beside solver-independent commands. It must not remain the long-term canonical generic meaning.

Do not rename it in the RFC PR. The implementation phase must choose one of:

- retire it after external realization is operational; or
- redefine a generic realization/adapter-request command only if that operation has a stable cross-solver contract.

A compatibility alias must not preserve local MOOSE ownership indefinitely.

### Future `run`

`physics run` should eventually:

1. compile Physics research intent;
2. resolve the canonical SOL model/realization request;
3. invoke the stable SOL runtime consumer;
4. let SOL runtime bootstrap/select the adapter;
5. validate;
6. execute authoritatively;
7. ingest returned evidence/provenance into Physics evidence semantics.

It must not fall back to a campaign runner or direct local MOOSE lowerer.

## 9. Migration sequence

### M2a-0 — freeze architecture debt

- add the #274 architecture guard;
- permit exactly the known semantic gateway -> local MOOSE transitional edge;
- forbid growth of that semantic edge set;
- forbid obvious local runtime/transport/registry owners;
- prevent `ExecutionPlan` from absorbing SOL/MOOSE contract identities.

### M2a-1 — canonical model contract

Establish the canonical SOL identity/artifact for the first Physics model slice. This is a prerequisite for production RealizationSpec construction.

### M2a-2 — semantic parameter/unit contract

Make every realization-bound value typed by semantic parameter and unit through the canonical model contract.

### M2a-3 — SOL request compiler / upstream consumer boundary

Define where Physics research actions meet the canonical SOL model and produce a validated `BackendTarget + MappingPlan + RealizationSpec`.

Do not implement this as a lossy `ExecutionPlan` field copy.

### M2a-4 — stable SOL runtime consumer

Add or adopt an upstream `simulation-ontology` CLI/API that owns `sol-adapter-runtime` use. Pin the consumed revision/artifact.

### M2a-5 — Physics gateway cutover

Replace:

```text
gateway.py -> MooseTargetIR / lower_execution_plan
```

with the accepted SOL boundary.

At this point the #274 guard tightens the allowed semantic MOOSE edge count from one to zero.

### M3 — MOOSE_GENERIC extraction

Characterize and migrate reusable MOOSE-specific mechanics to `sol-adapter-moose` in bounded batches.

Do not move modules merely because they live under `adapters/moose`; split MIXED ownership first.

### M4 — plasma realization coverage

Extend canonical SOL model/Public Contract capability only for demonstrated Physics needs. Preserve semantic types/units/scopes and do not leak MOOSE object names upstream.

### M5 — local MOOSE realization retirement

Retire `physics_harness/adapters/moose/target.py` after:

- external request parity;
- external adapter realization parity;
- construction/failure/evidence parity;
- stable runtime consumer;
- no remaining canonical callers.

### M6 — complete local adapter cleanup

Only after all remaining MOOSE_GENERIC and MIXED owners have migrated or been intentionally retained under a reviewed exception may the local adapter package be removed.

## 10. Validation strategy

This refactor changes architecture ownership, not plasma physics.

### RFC / guard PR

```text
P0 architecture guard self-test
P1 static architecture guard
Repository CI
CodeRabbit review
Scientific EVR = 0
```

### Later request/compiler implementation

Require positive and negative semantic controls:

- complete canonical model -> valid request;
- missing unit -> reject;
- missing relation/scope -> reject;
- unsupported capability mapping -> reject;
- renamed action IDs with unchanged semantic graph -> same realization meaning;
- MOOSE spelling injected upstream -> reject.

### Runtime cutover

Require:

- live `describe_adapter` evidence;
- explicit 0.2 compatibility;
- capability satisfaction;
- validate/execute separation;
- execute response-loss no-replay behavior;
- current local-vs-external construction parity;
- no scientific PASS inferred from protocol conformance alone.

## 11. Review questions for CodeRabbit

Please review the architecture, not just Markdown style.

1. Does this create any duplicate owner already present in `simulation-ontology`?
2. Is any Physics field incorrectly classified as safe to serialize into SOL?
3. Are the information gaps sufficient to prevent a lossy ExecutionPlan -> RealizationSpec shortcut?
4. Is the transitional-edge guard too weak, too brittle, or likely to hide a second dependency route?
5. Is the CLI migration plan compatible with a clean final API?
6. Are there responsibilities assigned to `sol-adapter-moose` that should remain upstream?
7. Does the migration order permit a temporary dual-authority state that should be forbidden?
8. Are there missing rollback/parity gates before retiring the local MOOSE target?
9. Can the cross-repository contract be made simpler without recreating runtime/transport logic?

## 12. Frozen invariants for this RFC

```text
PHYSICS_EXECUTION_PLAN_IS_SOL_MAPPING_PLAN = false
PHYSICS_EXECUTION_CASE_IS_SOL_MAPPING_ACTION = false
UNTYPED_PARAMETER_IS_SOL_QUANTITY = false
ACTION_NAME_IS_REALIZATION_SEMANTICS = false
LOCAL_PHYSICS_ADAPTER_RUNTIME_OWNER_COUNT = 0
LOCAL_PHYSICS_ADAPTER_TRANSPORT_OWNER_COUNT = 0
LOCAL_PHYSICS_ADAPTER_REGISTRY_OWNER_COUNT = 0
SOL_ADAPTER_RUNTIME_REUSE_REQUIRED = true
SEMANTIC_CONTROL_PLANE_DIRECT_MOOSE_EDGE_COUNT = 1 transitional
FINAL_SEMANTIC_CONTROL_PLANE_DIRECT_MOOSE_EDGE_TARGET = 0
MOOSE_REALIZATION_LONG_TERM_OWNER = sol-adapter-moose
PROTOCOL_CONFORMANCE_IMPLIES_SCIENTIFIC_PASS = false
```
