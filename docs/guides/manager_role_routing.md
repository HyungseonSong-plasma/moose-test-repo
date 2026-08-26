# Manager Role Routing and Preflight Orchestration

**Status:** living guide  
**Scope:** MOOSE/QPX technical work management  
**Purpose:** route each user request to the right reasoning role, require the right evidence contract, and prevent avoidable runtime/debugging rounds before external execution.

## 1. Manager is the default orchestrator

The Manager does not treat every technical request as the same kind of work. Before acting, classify the request and route it to the role whose evidence standard matches the question.

The Manager owns:

- request classification;
- role selection;
- sequencing or parallelization of roles;
- issue/work-state coordination;
- acceptance criteria;
- pre-execution validation;
- deciding when external QPX execution is justified;
- integrating Researcher and Validator findings into the next technical action;
- recording attributable Researcher -> Validator rounds as `RVR` so their effect on later EVR/DBR/RWR can be measured.

The Manager should not bypass a specialist role merely because an immediate answer appears plausible.

## 2. Role routing policy

### Researcher

Route to the Researcher when the question depends materially on external or source evidence, including:

- literature or experimental values;
- Mutation++ / MOOSE / QPX source behavior;
- collision/transport data provenance;
- physical-model alternatives;
- reference implementations;
- determining whether an approximation is justified;
- determining which independent state variables an upstream model actually depends on.

Researcher output contract:

```text
question
sources / revision
source-derived facts
inferences / assumptions
uncertainties
recommended engineering implication
```

### Validator

Route to the Validator when the question asks whether work is sufficiently verified, including:

- whether a test set is complete;
- whether acceptance criteria are strong enough;
- whether a proposed result is sufficient to close a gate;
- whether a regression can detect the intended defect;
- whether a production path, fallback, or approximation is independently validated;
- whether a target data/runtime representation can actually express the source model;
- whether a bundle is safe to deliver for external execution.

Validator output contract:

```text
scope under validation
covered failure classes
uncovered failure classes
false-PASS risks
required additions
acceptance decision
```

### Diagnostic / implementation worker

Route runtime errors, parser errors, solver failures, code construction failures, and implementation changes to the diagnostic/implementation path.

Examples:

- missing functor;
- duplicate MOOSE block;
- parser symbol collision;
- invalid parameter type;
- residual/Jacobian mismatch;
- nonlinear convergence failure;
- runtime output mismatch.

The diagnostic worker must use the predictive-batch protocol rather than immediately changing physics.

## 3. Mixed questions

Many requests require more than one role.

### Research then validation

Use when a test or model depends on external evidence:

```text
Manager
  -> Researcher: establish reference / source truth
  -> Validator: decide whether proposed test coverage is sufficient
  -> implementation / batch construction
```

When this sequence produces a material engineering/acceptance decision and is attributable to the work item, increment `RVR` by one.

### Parallel research and validation

Use when the Validator can audit structural coverage while the Researcher independently checks external facts. If their outputs converge into one recorded acceptance decision, count it as one `RVR`, not two.

### Runtime error with uncertain framework contract

```text
Manager
  -> Diagnostic worker: isolate construction/runtime failure
  -> Researcher: inspect framework/source contract only if the error signature leaves ambiguity
  -> Validator: confirm the fix and regression are sufficient before promotion
```

Do not increment `RVR` merely because a source file was consulted during debugging. `RVR` requires a material research question plus an explicit validation decision.

### Representation-adequacy uncertainty

Use when an upstream physics model is being collapsed into a simpler data/runtime representation.

```text
Manager
  -> Researcher: inventory source-model state variables and discrete branches
  -> Validator: test whether the proposed target schema can represent them within tolerance
       ├─ adequate -> proceed with data extraction/tabulation
       └─ inadequate -> architecture/model-interface change
```

This is a canonical `RVR` case because the research result directly determines the representation/implementation path.

Example:

```text
upstream: Q = Q(T, Te, ne, interaction_type)
target:   Q = table(T)
```

If changing `Te`, `ne`, or the interaction branch at fixed `T` materially changes `Q`, do not respond by making the one-dimensional table denser. Classify the result as `REPRESENTATION_ADEQUACY_FAIL` and route to an architecture change.

## 4. Mandatory pre-execution gate for MOOSE/QPX bundles

Before any full QPX physics run, every delivered MOOSE/QPX batch must pass a construction preflight.

Required order:

```text
P0 validator/checker self-test
P1 static input checks
P2 qpx-opt --check-input
P3 only then full runtime / physics validation
```

A failure in P0-P2 is a harness/construction failure and must not be interpreted as physics evidence.

## 5. Static construction checks

The standard preflight should include, when applicable:

- duplicate block detection;
- reserved parser-symbol detection;
- required input/output file existence;
- functor dependency graph resolution;
- generated dot-functor resolution;
- variable/material property naming consistency;
- alias target validity;
- pair-key canonicalization;
- expected output/postprocessor presence.

### Functor dependency rule

For a generic functor material property named `X_state` with `define_dot_functors = true`, the expected generated time-derivative functor is:

```text
dX_state_dt
```

Therefore a request such as:

```text
No functor ever provided with name 'dO_state_dt',
which was requested by 'dMn_dt_chain'.
```

should be caught before a full solve by checking whether the requested functor exists in the static provider graph and by running `qpx-opt --check-input`.

If the provider is actually named `w_O_state`, the generated dot functor is `dw_O_state_dt`, not `dO_state_dt`.

## 6. Checker validation

A checker is not trusted merely because it exists. It must include negative controls / mutation tests proving it detects its target defect.

Examples for a functor checker:

```text
valid generated dot functor              -> PASS
define_dot_functors disabled             -> FAIL
provider/request naming mismatch         -> FAIL
unknown ordinary functor                 -> FAIL
valid variable dependency                -> PASS
```

This is the same principle as Batch-A validator mutation testing: validate the validator.

## 7. External-runtime policy

`qpx-opt` runtime validation occurs only in the user's real MOOSE/QPX environment.

- GitHub Actions must not be used as QPX physics PASS/FAIL evidence when `qpx-opt` is unavailable there.
- Static checks and source research may happen before external execution.
- `--check-input` should be packaged in the same user execution round as the intended batch whenever practical so preflight does not create an avoidable EVR.

The Manager should deliberately compare `RVR` and `EVR`: the working hypothesis is that stronger research validation before implementation can reduce downstream external validation repetitions, but this must be demonstrated empirically across comparable issues rather than assumed.

For work that predates the metric, reconstruct `RVR` only from explicit recorded Researcher/Validator evidence and label the result `reconstructed` or `estimated`.

## 8. Manager decision examples

### User asks: "Is A0-A5 enough?"

```text
Manager -> Validator
```

because this is a test-sufficiency/false-PASS question.

### User asks: "Can O2+ use O2 collision data?"

```text
Manager -> Researcher
         -> Validator if the answer affects canonical transport acceptance
```

If the Researcher result and Validator acceptance are both recorded and materially affect implementation, this counts as one `RVR`.

### User posts: "No functor ever provided with name ..."

```text
Manager -> static construction preflight
         -> qpx-opt --check-input discriminator
         -> targeted fix
         -> negative-control regression
```

Do not start by changing transport physics.

### Upstream model needs Te/ne but target database stores only T

```text
Manager -> Researcher: confirm source dependency
         -> Validator: quantify fixed-T sensitivity to omitted variables
         -> representation-adequacy decision
```

Do not build a denser `Q(T)` table until this gate passes. This sequence counts as one `RVR` when recorded against the work item.

## 9. Continuous improvement

At closure or after material rework, the Manager reviews Validator metrics:

- WCC / T-WCC;
- RVR;
- EVR;
- DBR;
- RWR;
- CLR;
- FBR.

Interpretation must include the relationship between research investment and validation burden. In particular, compare similar complexity/work types using pairs such as:

```text
(RVR, EVR)
(RVR, DBR)
(RVR, RWR)
```

A pattern of higher `RVR` with lower `EVR`/`DBR` can indicate that earlier research validation is reducing downstream iteration. A single work item is not sufficient to establish causality; retain raw counts and compare distributions over time.

Repeated avoidable construction errors should result in stronger preflight checks. Repeated research uncertainty should result in better source/provenance contracts. Repeated false-PASS risk should result in stronger Validator mutation tests. Representation failures should result in an earlier model-state dependency inventory before data extraction begins.

The goal is to move failures earlier in the pipeline, where they are cheaper and do not consume external runtime rounds.

## 10. Metric adoption note

`RVR` was adopted on 2026-08-26. From this point forward the Manager must include it in active technical issue metrics. Historical values may be backfilled only from explicit evidence and must be marked reconstructed/estimated when not prospectively counted.
