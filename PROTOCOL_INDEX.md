# MOOSE/Physics Protocol Index

**Status:** canonical consumer-local router under Paul  
**Purpose:** route only Physics/domain semantics and trigger the minimum required central skills.

Paul essential rules are already active. Generic deterministic mechanics are not redefined here.

## Primary local phase

Choose one primary semantic phase for the immediate obligation:

```text
PLAN
RESEARCH
IMPLEMENT
VALIDATE
CLOSE
```

Auxiliary local semantic pack:

```text
SCIENTIFIC_EXECUTION
```

Central skill triggers:

```text
MUTATE               -> repository-mutation
GOVERNED_WORK        -> governed-work
SCHEDULED_CONTROLLER -> state-refresh + controller-throughput + controller-lifecycle
GITHUB_ACTIONS_OBSERVATION -> github-actions-observation
```

All central skills come from `docs/operating_system/central_skills.json`.

## Routes

### ROUTE-01 — Meeting / scope

Primary phase: `PLAN` or no technical phase.

Use local mode semantics in `OPERATING_CORE.md`. Read only the domain material needed for the decision.

### ROUTE-02 — New technical issue / bounded work

Primary phase: `PLAN`.

Read relevant planning/diagnostic sections of `docs/protocols/problem_solving.md`.

Define the closure claim, dependencies, acceptance evidence, and next real gate. Do not create operating-metric obligations.

### ROUTE-03 — Source / literature / model / provenance uncertainty

Primary phase: `RESEARCH`.

Read the relevant Researcher/Validator portions of `problem_solving.md` and retrieve attributable source evidence.

### ROUTE-04 — Runtime / construction / solver / convergence / coupling failure

Primary phase: usually `VALIDATE`.

Read `validation.md`; add only the active model/regime material from `problem_solving.md`.

Use `TROUBLESHOOTING_INDEX.md` or a relevant incident record only when the symptom matches.

Add `SCIENTIFIC_EXECUTION` when the claim crosses model/numerical/framework/runtime/observation semantics.

### ROUTE-05 — Regression / checker / executable validation

Primary phase: `VALIDATE`.

Read `validation.md`. Add `IMPLEMENT` only while code/harness/checker implementation is the immediate obligation.

### ROUTE-06 — Closure / retrospective / incident record

Primary phase: `CLOSE`.

Closure uses the owning issue/milestone acceptance criteria and current validation evidence. No operating-process or rule-effectiveness accounting is required.

When a material incident is worth preserving, record factual evidence under the attributable issue or `docs/incidents/`. A reusable deterministic mechanics defect should be fixed in the owning central skill/guard; a Physics semantic defect should be fixed in its local owner.

### ROUTE-07 — Imported transport / thermo / chemistry data

Use `RESEARCH` while source/model/representation truth is unresolved; transition to `VALIDATE` for executable/data-pipeline acceptance.

### ROUTE-08 — Known recurring symptom

Load only the matching troubleshooting/incident evidence and the phase owner selected by the actual failure surface.

Historical incident records are evidence, not current STATE.

### ROUTE-09 — Repository mutation

Trigger central `repository-mutation` before the actual write.

The local `repository_mutation.md` file, when consulted, supplies consumer policy/authorization only; deterministic mutation mechanics come from the central skill.

### ROUTE-10 — Code / harness / script / checker implementation

Primary phase: `IMPLEMENT`.

Read `coding.md`; transition to `VALIDATE` before accepting executable behavior/results.

### ROUTE-11 — Scientific execution integrity

Auxiliary: `SCIENTIFIC_EXECUTION`.

Read `scientific_execution.md` only when intent/regime preservation across execution layers is material to the claim.

### ROUTE-12 — Milestone / multi-issue capability delivery

Read `milestone_delivery.md`.

Each issue remains an independent semantic/rollback boundary; milestone acceptance adds capability-level integration evidence.

### ROUTE-13 — Scheduled controller

Trigger central state-refresh, controller-throughput, and controller-lifecycle from the exact Paul pin.

The central skills decide generic liveness/lifecycle mechanics. This repository decides Physics dependency readiness, resource meaning, and scientific HOLD/PASS semantics.


### ROUTE-14 — GitHub Actions observation

Trigger central `github-actions-observation` when the immediate obligation requires dispatching or correlating a GitHub Actions run, checking eventual-consistency visibility, or distinguishing the exact run/attempt for current CI or governed execution evidence.

The central skill owns dispatch/observation mechanics only. Physics acceptance, runtime/scientific meaning, dependency readiness, and PASS/HOLD decisions remain local.

## Paul rule-reuse gate

Before adding a repeated operating rule, classify it:

```text
cross-repository authority/claim invariant -> propose Paul essential rule
portable deterministic procedure          -> central skill
Physics-specific semantic/acceptance rule -> existing/new local owner
historical observation                    -> issue/incident/archive, not a rule
```

Do not restore Calvin rule-load scoring or operating metrics to decide whether a rule is useful.

## Local canonical owners

- Physics always-active invariants -> `OPERATING_CORE.md`
- local rule/skill activation -> `docs/protocols/rule_working_set.md`
- owner discovery -> `docs/rules/INVENTORY.md`
- planning/model/regime meaning -> `problem_solving.md`
- implementation -> `coding.md`
- validation/P0-P3 -> `validation.md`
- scientific execution integrity -> `scientific_execution.md`
- milestone delivery -> `milestone_delivery.md`
- mutation policy overlay -> `repository_mutation.md`
- symptom knowledge -> `docs/knowledge/TROUBLESHOOTING_INDEX.md`
- current STATE -> active issue body/status

Calvin operating metrics are archived under `archive/operating_metrics/`; they have no live owner.
