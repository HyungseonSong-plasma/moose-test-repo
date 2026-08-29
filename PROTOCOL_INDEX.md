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

## Canonical ownership map

- Operating invariants and authorization semantics -> `OPERATING_CORE.md`
- Request routing and rule-reuse decisions -> `PROTOCOL_INDEX.md`
- Phase 0, hypothesis design, Researcher/Validator orchestration, 3-EVR state machine, convergence/coupling diagnostic strategy -> `docs/protocols/problem_solving.md`
- P0-P3, static construction checks, predictive batch design, analyzer/checker self-validation, production parity, data A0-A7 -> `docs/protocols/validation.md`
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
