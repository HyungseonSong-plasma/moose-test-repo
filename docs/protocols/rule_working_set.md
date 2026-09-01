# Adaptive Rule Working-Set Protocol

**Status:** canonical procedure  
**Scope:** rule loading, unloading, phase packs, temporary diagnostics, and rule-context sizing  
**Purpose:** maximize local decision quality with the smallest relevant active rule set instead of attempting universal simultaneous rule coverage.

## RWS-01 — Operating objective

Do not optimize for global rule completeness. Optimize for:

```text
minimum active rule load
subject to
acceptable decision, prevention, and closure quality for the current phase
```

The rule inventory may grow. The active working set should remain small and phase-specific.

## RWS-02 — Working-set layers

Use three layers:

```text
CORE PACK
  always-active invariants only

PHASE PACK
  rules required by the current development/operation phase

TEMPORARY DIAGNOSTIC PACK
  incident-, symptom-, or hypothesis-specific rules loaded only while the signal remains material
```

Rules outside these layers remain in the inventory and are not loaded merely because they exist.

## RWS-03 — Context-size heuristic

The following is an engineering heuristic for this repository, not a model hard limit:

```text
Core pack:                  5-8 active invariants
Primary phase pack:         5-10 material rules/contracts
Temporary diagnostic pack: 0-4 material rules/contracts
Typical total:              12-20 material active rules/contracts
Review threshold:           ~25 weighted rule-load units
```

When rules differ strongly in complexity, estimate weighted load:

```text
simple invariant or direct gate              = 1
triggered rule with one material judgment    = 2
branch-heavy rule with exceptions/dependencies = 3
```

Interpretation:

```text
weighted load <= 18  -> GREEN
19-24                -> YELLOW; remove redundant/non-current material
>= 25                -> RED; split, unload, or refactor before adding more context
```

Do not treat these numbers as capability claims about the underlying model. They are repository operating thresholds intended to reduce rule interference and routing errors.

## RWS-04 — Canonical phase packs

Use the smallest applicable primary pack.

### PLAN

Typical concerns:

```text
scope
closure claim
issue/current-state identity
work decomposition
evidence requirement
research-vs-execution routing
```

Primary owners: `PROTOCOL_INDEX.md`, `docs/protocols/problem_solving.md`.

### RESEARCH

Typical concerns:

```text
source truth
provenance
model assumptions
regime validity
representation adequacy
independent evidence
```

Primary owner: Researcher/Validator portions of `docs/protocols/problem_solving.md`.

### IMPLEMENT

Typical concerns:

```text
ownership
reuse
canonical implementation point
generator/schema constraints
self-test structure
CLI/interface stability
repository mutation when a write is actually required
```

Primary owners: `docs/protocols/coding.md`; add `docs/protocols/repository_mutation.md` only for an actual repository-write step.

### VALIDATE

Typical concerns:

```text
P0 -> P3
semantic equivalence
production-path parity
numerical contract
environment identity
observation timing
checker self-test
negative/mutation controls
```

Primary owner: `docs/protocols/validation.md`; add `docs/protocols/scientific_execution.md` when the claim depends on intent/regime preservation across execution layers.

### CLOSE

Typical concerns:

```text
closure quality
work metrics
incident learning status
prevention KPIs
enforcement-promotion decisions
knowledge promotion
```

Primary owner: `docs/protocols/metrics_closure.md`.

## RWS-05 — Load triggers

Strong transition signals include:

```text
new bounded objective accepted
  -> PLAN

material source/model/provenance uncertainty
  -> RESEARCH

code/harness/script/checker construction or modification
  -> IMPLEMENT

executable batch/checker/runtime evidence or scientific PASS/FAIL claim
  -> VALIDATE

technical acceptance, retrospective, metrics, or incident-learning decision
  -> CLOSE
```

Add temporary diagnostic material when a symptom, incident signature, or hypothesis requires it. Search `docs/knowledge/TROUBLESHOOTING_INDEX.md`, `docs/incidents/`, or `docs/metrics/incidents/` only when triggered by the current signal.

## RWS-05A — Incident auto-activation and recording trigger

A material incident is itself a working-set trigger. The model must detect and route this trigger autonomously; activation must not depend on the user asking whether the incident was recorded.

Treat an event as a material incident when current evidence establishes an operational or technical failure that requires recovery, classification, or reusable prevention learning, including examples such as:

```text
wrong-resource / wrong-action repository mutation
false PASS / false FAIL
assistant-caused rework or artifact corruption
known gate bypass or gate defect
unexpected runtime/environment escape that changes classification
recurrent failure covered by an existing canonical rule
```

Routine warnings, harmless wording corrections, or exploratory dead ends with no material operational consequence do not automatically become incident records.

When a material incident is detected, activate a temporary incident-learning pack even if the primary phase remains PLAN, IMPLEMENT, or VALIDATE:

```text
TEMPORARY INCIDENT-LEARNING PACK
  docs/incidents/                         -> individual evidence narrative
  docs/protocols/metrics_closure.md       -> MET-20 / MET-21 / MET-22 classification and prevention decision
  docs/metrics/incidents/learning_ledger.md -> prospective incident-level record
  relevant semantic/gate owner            -> root-cause and recurrence evidence
```

Required autonomous routing:

```text
1. detect the material incident from current evidence;
2. activate the incident-learning pack without waiting for a user prompt;
3. preserve or link the individual incident evidence under docs/incidents/ or the attributable issue;
4. once incident-level evidence is sufficient, append the prospective MET-20 row to learning_ledger.md;
5. when MET-22 triggers, record the EPR decision and prevention maturity;
6. record whether the relevant rule/pack was active at the incident so routing misses remain measurable;
7. unload the temporary incident-learning pack only after the recording/classification obligations are resolved or explicitly marked UNRESOLVED.
```

If the event is clearly an incident but the learning status is not yet distinguishable, activate the pack immediately and preserve the evidence; use `UNRESOLVED` only when the canonical MET-20 discriminator cannot yet be established. Do not postpone activation merely because classification is incomplete.

This is a routing rule, not a new root-cause taxonomy. Reuse the existing incident and MET-20/MET-22 semantic owners rather than creating a duplicate incident protocol.

## RWS-06 — Unload rule

Rule activation is not monotonic accumulation.

```text
phase exits
  -> unload the prior phase pack unless an unresolved obligation still depends on it

incident/hypothesis resolved
  -> unload its temporary diagnostic pack

new phase begins
  -> construct a fresh working set from CORE + new phase + unresolved material obligations
```

Do not carry a rule into later phases merely because it was useful earlier.

## RWS-07 — Expansion signals

Do not preload inventory material "just in case." Expand the working set only when one of these occurs:

```text
current pack fails to explain/discriminate the material failure twice under the same bounded hypothesis space
failure evidence crosses into another semantic layer
known incident signature appears
an unresolved obligation explicitly routes to another owner
current rule/gate applicability is uncertain and can change the decision
```

Expansion is temporary unless the current phase itself changes.

## RWS-08 — Shrink after expansion

After a temporary expansion:

```text
resolve the discriminator
record any accepted decision/evidence
route only remaining obligations
unload no-longer-material rules
return below the working-set review threshold
```

The system should expand to investigate and contract after resolution.

## RWS-09 — Inventory lookup before new rule creation

Before creating a new rule because the active pack appears insufficient:

```text
1. check the rule inventory for a dormant owner;
2. check whether the issue is RULE_EXISTS_BUT_NOT_LOADED / trigger-routing failure;
3. check whether an existing gate was bypassed or defective;
4. apply the PROTOCOL_INDEX rule-reuse gate;
5. create or extend a canonical rule only when no existing owner covers the semantic failure.
```

A dormant but relevant rule should normally be activated or its trigger repaired, not duplicated.

## RWS-10 — Working-set failure interpretation

When a known failure occurs, distinguish:

```text
rule absent
rule exists but was not loaded
rule loaded but applicability trigger was missed
rule/gate invoked but defective
rule/gate valid but environment identity escaped
```

`rule exists but was not loaded` and missed applicability are routing/enforcement failures, not evidence that another semantic rule is needed. Map them into the existing MET-20/MET-22 prevention-learning framework rather than creating another taxonomy.

## RWS-11 — Phase transition record

For material technical work, maintain a lightweight current working-set declaration in the active issue/status context when useful:

```text
Current phase: PLAN | RESEARCH | IMPLEMENT | VALIDATE | CLOSE
Active phase pack: <owner(s)>
Temporary diagnostic pack: <none or explicit symptom/incident refs>
Unresolved cross-phase obligations: <none or explicit obligations>
```

Do not copy rule text into the issue. Record only owner IDs/paths and state.

## RWS-12 — Bootstrap rule

`moose-test-init` restores enough context to resume safely, not every repository rule.

Bootstrap should load:

```text
1. OPERATING_CORE.md
2. active issue/current-state checkpoint
3. PROTOCOL_INDEX.md
4. this rule-working-set protocol
5. the phase pack selected for the immediate resume obligation
6. only triggered temporary diagnostic evidence
```

Do not load all technical protocols during bootstrap. If the phase changes later, load the new pack at that transition.
