# Workspace Operating Boundary

This repository is reserved for MOOSE/Physics development, regression, verification, troubleshooting, and operating-system evidence.

## Cross-chat entry

For a fresh chat, use:

```text
moose-test-init
```

`BOOTSTRAP.md` is the canonical cross-chat entry point. It restores the minimum safe operating context from repository state rather than relying on prior-chat memory.

## Adaptive operating architecture

Canonical operating rules are not duplicated here. The operating stack is:

```text
BOOTSTRAP.md                       -> cross-chat initialization
OPERATING_CORE.md                  -> always-active invariants
PROTOCOL_INDEX.md                  -> phase / obligation router
docs/protocols/rule_working_set.md -> dynamic load / unload policy
docs/rules/INVENTORY.md            -> dormant rule-owner locator
active issue/body                   -> current STATE
phase protocol                      -> current procedure
```

Primary phase packs are:

```text
PLAN
RESEARCH
IMPLEMENT
VALIDATE
CLOSE
```

`MUTATE` and `SCIENTIFIC_EXECUTION` are auxiliary packs loaded only when triggered. Incident/knowledge material is temporary diagnostic context, not an always-active rule set.

The operating objective is not universal simultaneous rule coverage. Maintain the smallest relevant rule working set for the current phase and re-evaluate it when user intent, evidence, symptoms, or unresolved obligations change.

## Canonical technical owners

Use only when their phase/trigger is active:

- `docs/protocols/problem_solving.md` — planning, diagnosis framing, research/model-regime work, bounded problem solving, and 3-EVR workflow;
- `docs/protocols/coding.md` — code/harness/script/checker implementation;
- `docs/protocols/validation.md` — P0-P3, checker/analyzer, production-path, runtime-semantic, and data validation;
- `docs/protocols/scientific_execution.md` — cross-layer intent/regime preservation for executable scientific claims;
- `docs/protocols/metrics_closure.md` — closure metrics, incident learning, recurrence, and enforcement promotion;
- `docs/protocols/repository_mutation.md` — repository write safety for the immediate mutation step;
- `docs/knowledge/TROUBLESHOOTING_INDEX.md` — reusable symptom-specific knowledge loaded only on matching signals.

## State and evidence

For current work state, use the active GitHub issue body/current status block. Issue comments are chronological evidence, not canonical current state.

Repository content may include MOOSE/Physics regression inputs, minimal reproducers, checkers/reference data, incident/development logs, scripts, and compatible local test executables.

Current runtime naming is `Physics` / `physics-opt`. Historical incident records, archived experiments, immutable snapshots, or old closure evidence may retain `QPX` / `qpx-opt` when those names identify what was actually executed at the time; those historical names do not redefine the current runtime owner.

Production source changes belong in the appropriate source repository. This workspace primarily stores test/development evidence and small source deltas only when needed to reproduce or document an investigation.