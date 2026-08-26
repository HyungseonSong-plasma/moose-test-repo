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

Load `docs/protocols/problem_solving.md` only when converting lessons into a new solving rule.

### ROUTE-07 — Imported transport / thermo / chemistry data
Read:
- `docs/protocols/problem_solving.md` for source/model/representation gates
- `docs/protocols/validation.md` for A0-A7 data-pipeline validation

### ROUTE-08 — Known recurring symptom
Read:
- `docs/knowledge/TROUBLESHOOTING_INDEX.md`
- then the procedure selected by the symptom class

Knowledge is evidence, not current STATE.

## Canonical ownership map

- Operating invariants and authorization semantics -> `OPERATING_CORE.md`
- Request routing -> `PROTOCOL_INDEX.md`
- Phase 0, hypothesis design, Researcher/Validator orchestration, 3-EVR state machine, convergence/coupling diagnostic strategy -> `docs/protocols/problem_solving.md`
- P0-P3, static construction checks, predictive batch design, analyzer/checker self-validation, production parity, data A0-A7 -> `docs/protocols/validation.md`
- WCC/T-WCC/RVR/EVR/DBR/RWR/CLR/FBR, work boundaries, closure and retrospectives -> `docs/protocols/metrics_closure.md`
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

## Rule creation rule

Before adding a new guide or rule:

1. identify the canonical owner above;
2. modify an existing canonical rule if possible;
3. create a new Rule ID only if the behavior is materially distinct;
4. create a new protocol document only if no existing module can own the responsibility without mixing concerns.

This prevents rule proliferation and stale copies.