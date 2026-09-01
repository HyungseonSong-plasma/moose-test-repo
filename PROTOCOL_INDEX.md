# MOOSE/QPX Protocol Index

**Status:** canonical router  
**Purpose:** select the minimum procedure set required for the current request and current development phase.

Always read `OPERATING_CORE.md` first. Use `docs/protocols/rule_working_set.md` to keep the active rule context bounded. Consult `docs/rules/INVENTORY.md` only when the appropriate dormant owner is unclear or a trigger indicates inventory expansion.

## Primary phase selection

Choose one primary phase for the immediate obligation:

```text
PLAN
RESEARCH
IMPLEMENT
VALIDATE
CLOSE
```

`MUTATE` is an adjacent short-lived pack used only for actual repository writes. `SCIENTIFIC_EXECUTION` is an auxiliary pack loaded only when cross-layer intent/regime preservation is material to an executable scientific claim.

Do not keep a previous phase pack active merely because it was used earlier. Preserve only unresolved material obligations across transitions.

## Routing table

### ROUTE-01 — Meeting / governance / scope
Primary phase: `PLAN` or no technical phase.

Read only what the discussion requires. When the user says `meeting`, CORE-02 prohibits mutation.

### ROUTE-02 — New technical issue or bounded work package
Primary phase: `PLAN`.

Read:
- relevant planning/diagnostic sections of `docs/protocols/problem_solving.md`

Load `docs/protocols/metrics_closure.md` only when work-boundary metrics or closure-contract construction is currently material, not by default at issue creation.

### ROUTE-03 — Source / literature / model / provenance / representation uncertainty
Primary phase: `RESEARCH`.

Read:
- Researcher/Validator sections of `docs/protocols/problem_solving.md`

Retrieve source/reference evidence as needed. If the result changes implementation or acceptance, record the attributable research-validation decision under the existing metrics contract.

### ROUTE-04 — Runtime, parser, construction, solver, convergence, or coupling failure
Primary phase: usually `VALIDATE`; use `PLAN` first only when the hypothesis space itself is unresolved.

Read:
- `docs/protocols/validation.md` for classification/gates
- `docs/protocols/problem_solving.md` only for active hypothesis/model-regime obligations

Load temporary diagnostic evidence from `docs/knowledge/TROUBLESHOOTING_INDEX.md` or `docs/incidents/` only when the symptom matches or prior RCA is needed.

Add `SCIENTIFIC_EXECUTION` when the failure crosses model/numerical/framework/runtime/observation semantics.

### ROUTE-05 — Test bundle / checker / canonical regression construction
Primary phase: `VALIDATE`.

Read:
- `docs/protocols/validation.md`

Add `IMPLEMENT` only while actual checker/harness/script code is being modified. Unload it when implementation is complete and validation becomes primary again.

### ROUTE-06 — Metrics, closure, retrospective, incident learning, or efficiency analysis
Primary phase: `CLOSE`.

Read:
- `docs/protocols/metrics_closure.md`

This route owns MET-20/MET-21/MET-22 incident learning and enforcement-promotion decisions. Load technical phase packs only when a retrospective exposes an unresolved technical obligation.

### ROUTE-07 — Imported transport / thermo / chemistry data
Primary phase: `RESEARCH` while source/model/representation truth is unresolved; transition to `VALIDATE` for A0-A7 pipeline acceptance.

Read only the currently required owner:
- `docs/protocols/problem_solving.md` for source/model/representation gates
- `docs/protocols/validation.md` for executable/data-pipeline validation

Do not keep both fully active after the transition unless an unresolved cross-phase obligation requires both.

### ROUTE-08 — Known recurring symptom
Primary phase: determined by the active failure surface.

Read:
- matching entry from `docs/knowledge/TROUBLESHOOTING_INDEX.md`
- then only the phase owner selected by that symptom

Knowledge is evidence, not current STATE and not an always-active pack.

### ROUTE-09 — Repository / issue / file mutation and state synchronization
Adjacent pack: `MUTATE`.

Read:
- `docs/protocols/repository_mutation.md`

Load this only immediately before an actual GitHub issue/file/branch/ref/comment mutation. Unload it after read-back verification unless another predeclared write remains the immediate next obligation.

### ROUTE-10 — Code / harness / script / checker implementation
Primary phase: `IMPLEMENT`.

Read:
- `docs/protocols/coding.md`

Add ROUTE-09 only for the actual repository-write step. Transition to `VALIDATE` before delivering or accepting executable behavior/results.

### ROUTE-11 — Scientific execution integrity
Auxiliary pack: `SCIENTIFIC_EXECUTION`.

Read:
- `docs/protocols/scientific_execution.md`

Trigger when a claim depends on preserving intent through:

```text
model
-> numerical regime
-> framework-effective configuration
-> runtime trajectory
-> observation/evidence
-> decision
```

Do not load this ontology merely because the repository is scientific; load it when one of those links is material to the current claim or failure.

### ROUTE-12 — Milestone / multi-issue capability delivery
Primary phase: `PLAN` when defining or restructuring the milestone; later transition through each issue's normal phase and return to `VALIDATE` / `CLOSE` for milestone integration and closure.

Read:
- `docs/protocols/milestone_delivery.md`

Trigger when multiple issues are intentionally composed to deliver one usable capability. Use milestone M0 to define the capability statement, dependency DAG, issue queue, integration risks, and milestone Definition of Done before large implementation fan-out.

Milestone batching does not replace issue-local acceptance or repository mutation safety. Each issue remains an independent semantic/rollback boundary; the milestone adds only capability-level planning and cross-issue integration acceptance.

## Standard obligation routing

```text
SOURCE_TRUTH          -> ROUTE-03 / RESEARCH
DIAGNOSIS             -> ROUTE-02 or ROUTE-04
MODEL_REGIME          -> RESEARCH or PLAN; problem_solving.md owns meaning
IMPLEMENTATION        -> ROUTE-10 / IMPLEMENT
EXECUTION_CONFORMANCE -> ROUTE-05 / VALIDATE; add ROUTE-11 when cross-layer semantics matter
VALIDATION            -> ROUTE-05 / VALIDATE
KNOWN_SYMPTOM         -> ROUTE-08 + selected phase pack
MUTATION              -> ROUTE-09 / MUTATE
CLOSURE_OR_REVIEW     -> ROUTE-06 / CLOSE
MILESTONE_DELIVERY    -> ROUTE-12 / PLAN -> issue phases -> VALIDATE/CLOSE
```

## Contract-chain resolution

Treat every loaded procedure as a contract:

```text
input  = current problem, accepted state, and existing evidence
output = decision plus zero or more unresolved obligations
```

Canonical flow:

```text
problem observed
-> apply CORE + current STATE
-> select primary phase
-> load that phase pack
-> apply the minimum selected contract
-> route only unresolved material obligations
-> temporarily expand when a trigger requires another owner
-> shrink again when the discriminator/obligation is resolved
-> transition phase when the immediate work changes
-> stop on explicit HOLD/BLOCKED or when no obligation remains
```

Chain invariants:

1. A downstream contract may refine an upstream decision but may not weaken a CORE invariant or erase accepted evidence without contradictory evidence.
2. Accepted outputs become inputs to the next contract; do not rediscover the same fact unless stale, contradicted, or identity-sensitive.
3. Resolve prerequisites before dependent obligations.
4. Reference downstream owners instead of copying procedure text.
5. If the active pack seems insufficient, apply `rule_working_set.md` inventory lookup before creating a new rule.
6. For executable scientific claims, a downstream PASS must not bypass an unresolved material scientific-execution link.

## Rule-working-set escalation

Before adding another rule because a problem was missed, classify the miss:

```text
RULE_ABSENT
RULE_EXISTS_BUT_NOT_LOADED
TRIGGER_OR_ROUTING_MISSED
GATE_BYPASSED
GATE_DEFECT
ENVIRONMENT_ESCAPE
```

Only `RULE_ABSENT` is direct evidence for a genuinely missing semantic rule. The other classes require working-set, routing, enforcement, validator, or environment repair through existing owners.

Map incident learning to MET-20/MET-22; do not create a duplicate incident taxonomy here.

## Canonical ownership map

- Always-active invariants and authorization/state/evidence authority -> `OPERATING_CORE.md`
- Adaptive loading/unloading and working-set size -> `docs/protocols/rule_working_set.md`
- Dormant rule/pack discovery metadata -> `docs/rules/INVENTORY.md`
- Request routing and rule-reuse decisions -> `PROTOCOL_INDEX.md`
- Milestone capability delivery, issue DAG, integration, and milestone closure -> `docs/protocols/milestone_delivery.md`
- Scientific-execution integrity ontology -> `docs/protocols/scientific_execution.md`
- Planning, diagnosis, Researcher/Validator flow, EVR strategy, model/regime meaning -> `docs/protocols/problem_solving.md`
- Code/harness/script/checker implementation ownership -> `docs/protocols/coding.md`
- P0-P3, validation, checker self-tests, numerical/runtime gates, production parity -> `docs/protocols/validation.md`
- Work metrics, closure, incident learning, prevention KPIs, enforcement promotion -> `docs/protocols/metrics_closure.md`
- Repository mutation safety -> `docs/protocols/repository_mutation.md`
- Reusable symptom/fix knowledge -> `docs/knowledge/TROUBLESHOOTING_INDEX.md`
- Current work state -> active issue body/status
- Chronological incident evidence -> issue comments / `docs/incidents/`

## Legacy-guide mapping

Compatibility entry points must not contain independent canonical rule definitions:

- `docs/guides/manager_role_routing.md` -> this index + `docs/protocols/problem_solving.md`
- `docs/guides/multiphysics_problem_solving_protocol.md` -> `docs/protocols/problem_solving.md`
- `docs/guides/predictive_batch_test_design.md` -> `docs/protocols/validation.md`
- `docs/guides/three_evr_problem_solving_protocol.md` -> `docs/protocols/problem_solving.md`
- `docs/guides/work_closure_validator.md` -> `docs/protocols/metrics_closure.md`

## Rule-reuse gate

Prefer a small number of broad rules with explicit triggers over case-specific rule accumulation.

Before adding or extending any rule, protocol, or reusable knowledge entry:

1. check the active working set and `docs/rules/INVENTORY.md` for an existing owner;
2. if the lesson is already covered, add no semantic rule and fix only why it was missed: load selection, trigger, routing, enforcement, evidence identity, gate behavior, or environment;
3. if only partly covered, minimally extend the existing canonical owner;
4. create a new Rule ID/document only when the behavior is materially distinct and no existing owner can cover it without mixing responsibilities.

The goal is not universal simultaneous coverage. The goal is high local decision quality with a small active working set that can expand and contract as evidence changes.
