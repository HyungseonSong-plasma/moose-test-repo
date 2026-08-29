# MOOSE/QPX Protocol Index

**Status:** canonical router  
**Purpose:** select the minimum procedure set required for the current request.

Always read `OPERATING_CORE.md` first. Then use this file to load only the procedure(s) needed for the request.

## Routing table

### ROUTE-01 — Meeting / governance / scope
Read:
- `OPERATING_CORE.md`
- current issue body when an issue is referenced

Do not load technical procedures unless the discussion actually requires them.

### ROUTE-02 — New technical issue or bounded work package
Read:
- `docs/protocols/problem_solving.md`
- `docs/protocols/metrics_closure.md`

Add `docs/protocols/validation.md` before any executable batch is delivered.

### ROUTE-03 — Source / literature / model / provenance / representation question
Read:
- `docs/protocols/problem_solving.md` Researcher/Validator sections

Search source files and external/reference evidence as needed. If the result changes implementation or acceptance, record one attributable RVR.

### ROUTE-04 — Runtime, parser, construction, solver, convergence, coupling failure
Read:
- `docs/protocols/problem_solving.md`
- `docs/protocols/validation.md`

Search `docs/knowledge/TROUBLESHOOTING_INDEX.md` only for matching symptoms or reusable prior incidents.

### ROUTE-05 — Test bundle / checker / canonical regression construction
Read:
- `docs/protocols/validation.md`

Load `docs/protocols/problem_solving.md` only when hypothesis branching or EVR budgeting is needed.

### ROUTE-06 — Metrics, closure, retrospective, efficiency analysis
Read:
- `docs/protocols/metrics_closure.md`

Load `docs/protocols/problem_solving.md` only when converting a genuinely missing lesson into a solving rule. Any lesson promotion must first pass the rule-reuse gate below.

### ROUTE-07 — Imported transport / thermo / chemistry data
Read:
- `docs/protocols/problem_solving.md` for source/model/representation gates
- `docs/protocols/validation.md` for A0-A7 data-pipeline validation

### ROUTE-08 — Known recurring symptom
Read:
- `docs/knowledge/TROUBLESHOOTING_INDEX.md`
- then the procedure selected by the symptom class

Knowledge is evidence, not current STATE.

### ROUTE-09 — Repository / issue / file mutation and state synchronization
Read:
- `docs/protocols/repository_mutation.md`

Apply this route before any GitHub issue/file/branch/ref mutation, including dependency-status synchronization after issue lifecycle changes. Read/search operations do not require the mutation procedure unless they are preparing a write.

### ROUTE-10 — Code / harness / script / checker implementation
Read:
- `docs/protocols/coding.md`

Apply this route before creating, modifying, reviewing, or reorganizing repository code, harnesses, runners, scripts, checkers, or executable test orchestration.

Add `docs/protocols/validation.md` before delivering any new or changed executable command to the user. Add ROUTE-09 before repository writes. Coding structure/ownership decisions belong to this route; mutation mechanics belong to ROUTE-09.

## Contract-chain resolution

Treat every loaded rule or procedure as a contract:

```text
input  = current problem, accepted state, and existing evidence
output = decision plus zero or more unresolved obligations
```

Do not preload an entire rule graph. Apply the minimum current contract, then route only the unresolved obligation(s).

For executable scientific claims, CORE-16 is the top-level semantic contract. Its ontology links are routed to the existing owners rather than creating a parallel protocol tree.

Standard obligations:

```text
SOURCE_TRUTH          -> ROUTE-03
DIAGNOSIS             -> ROUTE-02 or ROUTE-04
MODEL_REGIME          -> ROUTE-02/ROUTE-03; problem_solving.md / PS-23 owns the meaning
IMPLEMENTATION        -> ROUTE-10; coding.md owns code/harness/script structure and reuse
EXECUTION_CONFORMANCE -> ROUTE-05; validation.md / VAL-21 owns preflight and runtime-semantic evidence
VALIDATION            -> ROUTE-05 and CORE-08 P0->P3
KNOWN_SYMPTOM         -> ROUTE-08
MUTATION              -> ROUTE-09
CLOSURE_OR_REVIEW     -> ROUTE-06
```

Canonical flow:

```text
problem observed
-> apply CORE invariants and current issue STATE
-> choose the initial ROUTE
-> apply the minimum selected rule/procedure
-> record its decision and unresolved obligation(s)
-> route each material obligation through this index
-> repeat until no obligation remains or an explicit HOLD/BLOCKED decision is reached
-> present the solution, validation result, or closure decision
```

Chain invariants:

1. A downstream contract may refine an upstream decision but may not weaken a CORE invariant or erase accepted evidence without contradictory evidence.
2. Accepted outputs become inputs to the next contract; do not rediscover the same fact unless it is stale, contradicted, or identity-sensitive.
3. Resolve prerequisites before dependent obligations. Batch independent obligations when doing so preserves interpretability and reduces external rounds.
4. Reference downstream routes/contracts instead of copying their procedure text into the current rule.
5. If no existing route can satisfy a material obligation, apply the rule-reuse gate before creating any new rule.
6. For executable claims, a downstream PASS must not bypass an unresolved material link in the CORE-16 scientific-execution ontology.

Example:

```text
solver/runtime problem
-> ROUTE-04: diagnose the failure class
-> SOURCE_TRUTH if framework/model behavior is uncertain
-> ROUTE-03: establish the source contract
-> MODEL_REGIME if the claim depends on scale/coupling/representation assumptions
-> IMPLEMENTATION when code/harness/test changes are required
-> ROUTE-10: choose the canonical owner, entry point, reuse boundary, and self-tests
-> MUTATION before repository writes
-> ROUTE-09: perform and verify the write
-> EXECUTION_CONFORMANCE to prove the intended regime can and did execute
-> VALIDATION when a candidate fix or claim must be tested
-> ROUTE-05: P0->P3 validation
-> CLOSURE_OR_REVIEW
-> ROUTE-06: metrics, retrospective, and closure
```

## Canonical ownership map

- Scientific-execution ontology and intent-preservation invariant -> `OPERATING_CORE.md` / CORE-16
- Operating invariants and authorization semantics -> `OPERATING_CORE.md`
- Request routing, contract-chain resolution, and rule-reuse decisions -> `PROTOCOL_INDEX.md`
- Code/harness/script/checker ownership, file placement, reuse, stable CLI design, phase-safe implementation, and implementation delivery gate -> `docs/protocols/coding.md`
- Phase 0, hypothesis design, Researcher/Validator orchestration, 3-EVR state machine, convergence/coupling diagnostic strategy, and model/scale/coupling regime meaning -> `docs/protocols/problem_solving.md` (including PS-23)
- P0-P3, static construction checks, predictive batch design, analyzer/checker self-validation, production parity, data A0-A7, numerical/framework preflight, and runtime-semantic conformance -> `docs/protocols/validation.md` (including VAL-21)
- WCC/T-WCC/RVR/EVR/DBR/RWR/CLR/FBR, work boundaries, closure and retrospectives -> `docs/protocols/metrics_closure.md`
- Repository/issue/file mutation safety, no-op prevention, and dependency fan-out synchronization -> `docs/protocols/repository_mutation.md`
- Reusable symptom/fix knowledge -> `docs/knowledge/TROUBLESHOOTING_INDEX.md`
- Current work state -> active issue body
- Chronological evidence -> issue comments / `docs/incidents/`

## Legacy-guide mapping

The following files are compatibility entry points only and must not contain independent canonical rule definitions:

- `docs/guides/manager_role_routing.md` -> `PROTOCOL_INDEX.md` + `docs/protocols/problem_solving.md`
- `docs/guides/multiphysics_problem_solving_protocol.md` -> `docs/protocols/problem_solving.md`
- `docs/guides/predictive_batch_test_design.md` -> `docs/protocols/validation.md`
- `docs/guides/three_evr_problem_solving_protocol.md` -> `docs/protocols/problem_solving.md`
- `docs/guides/work_closure_validator.md` -> `docs/protocols/metrics_closure.md`

## Rule-reuse gate

Prefer a small number of broad rules with explicit triggers over case-specific rule accumulation.

Before adding or extending any rule, protocol, or reusable knowledge entry:

1. compare the lesson against the nearest canonical owner and relevant existing knowledge;
2. if it is already covered, add nothing and fix only the reusable reason it was missed (routing, trigger, enforcement, state/evidence identity, or execution);
3. if it is only partly covered, minimally extend that existing owner;
4. create a new Rule ID or document only when the behavior is materially distinct and no existing owner can cover it without mixing responsibilities.

This is the canonical rule-creation and retrospective-novelty gate. Do not restate it in other protocols.
