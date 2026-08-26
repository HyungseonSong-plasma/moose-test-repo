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
- integrating Researcher and Validator findings into the next technical action.

The Manager should not bypass a specialist role merely because an immediate answer appears plausible.

## 2. Role routing policy

### Researcher

Route to the Researcher when the question depends materially on external or source evidence, including:

- literature or experimental values;
- Mutation++ / MOOSE / QPX source behavior;
- collision/transport data provenance;
- physical-model alternatives;
- reference implementations;
- determining whether an approximation is justified.

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

### Parallel research and validation

Use when the Validator can audit structural coverage while the Researcher independently checks external facts.

### Runtime error with uncertain framework contract

```text
Manager
  -> Diagnostic worker: isolate construction/runtime failure
  -> Researcher: inspect framework/source contract only if the error signature leaves ambiguity
  -> Validator: confirm the fix and regression are sufficient before promotion
```

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

### User posts: "No functor ever provided with name ..."

```text
Manager -> static construction preflight
         -> qpx-opt --check-input discriminator
         -> targeted fix
         -> negative-control regression
```

Do not start by changing transport physics.

## 9. Continuous improvement

At closure or after material rework, the Manager reviews Validator metrics:

- WCC / T-WCC;
- EVR;
- DBR;
- RWR;
- CLR;
- FBR.

Repeated avoidable construction errors should result in stronger preflight checks. Repeated research uncertainty should result in better source/provenance contracts. Repeated false-PASS risk should result in stronger Validator mutation tests.

The goal is to move failures earlier in the pipeline, where they are cheaper and do not consume external runtime rounds.
