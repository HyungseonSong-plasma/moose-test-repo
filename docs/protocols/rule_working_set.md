# Samuel Local Rule / Skill Working Set

**Status:** canonical consumer routing policy under Samuel  
**Purpose:** keep the live context semantic and trigger-driven without Calvin rule-load scoring.

## RWS-01 — Composition

Use:

```text
Samuel ESSENTIAL_RULES
+ MOOSE/Physics OPERATING_CORE
+ one primary local semantic phase owner
+ only triggered central skills/capabilities
+ durable Samuel controller state only when required
+ temporary diagnostic evidence only when required
```

Do not preload every local protocol or every central skill.

## RWS-02 — Local phase owners

```text
PLAN       -> problem_solving.md
RESEARCH   -> problem_solving.md research/model/source sections
IMPLEMENT  -> coding.md
VALIDATE   -> validation.md
CLOSE      -> current acceptance evidence; validation.md or milestone_delivery.md when applicable
```

`scientific_execution.md` is auxiliary and loaded only for cross-layer scientific intent/regime claims.

## RWS-03 — Central skill/capability triggers

Read exact identities from `central_skills.json`; capability provider order comes from the pinned central capability registry.

```text
INIT
  -> session-bootstrap
  -> state-refresh

MUTATE
  -> repository-mutation

GOVERNED_WORK
  -> governed-work

SCHEDULED_CONTROLLER
  -> state-refresh
  -> controller-throughput
  -> controller-lifecycle

RESEARCH_CONTROLLER
  -> research-controller

GITHUB_ACTIONS_EXECUTION
  -> github-actions-execution

GITHUB_ACTIONS_OBSERVATION
  -> github-actions-observation

GITHUB_PR_MERGE
  -> pull-request-merge

ARTIFACT_STAGING
  -> artifact-staging

SCIENTIFIC_DISCRIMINATOR_CONTROLLER
  -> scientific-discriminator-controller
```

Skill presence does not imply permanent activation.

## RWS-04 — Transition

When the immediate obligation changes, unload local material that is no longer needed and load the new semantic owner/triggered skill.

Preserve unresolved cross-phase obligations by reference, not by keeping entire old protocols in context.

## RWS-05 — Diagnostic expansion

Load troubleshooting or incident evidence only when a current symptom/hypothesis requires it.

After the discriminator is resolved, preserve the accepted evidence and drop the temporary diagnostic material.

## RWS-06 — New-rule classification

Before creating a new rule:

1. check whether the missing behavior is already a Samuel essential rule;
2. if it is deterministic and portable, delegate it to a central skill/controller path instead of adding procedural prose;
3. if it is Physics-specific semantic/acceptance meaning, use the narrowest existing local owner;
4. if it is only a historical observation, record it as evidence rather than a rule.

No numeric rule-load score, activation percentage, or rule-efficiency metric is used.

## RWS-07 — Bootstrap

`moose-test-init` follows `BOOTSTRAP.md` and the central `session-bootstrap` skill.

Bootstrap loads Samuel essential rules, verifies central catalog/capability metadata, restores the local Physics core/current STATE, selects one local semantic phase owner, and loads only the central skills needed for the immediate obligation. Initialization remains read-only.

## RWS-08 — Scheduled-controller resume

A scheduled controller resumes from durable state through central `state-refresh`, `controller-throughput`, and `controller-lifecycle`; `research-controller` is triggered only when the durable generic controller owns the current obligation.

Physics-specific dependency readiness, validation lineage meaning, and scientific gates stay local.

## Historical Calvin/Paul policy

The prior adaptive weighted working-set policy and its metrics are historical Calvin evidence. Paul established the minimal-rule / skill-delegation architecture; Samuel succeeds it with durable controller and capability routing. Historical records are preserved under `archive/operating_metrics/` and central immutable version baselines, and are not live Samuel inputs.
