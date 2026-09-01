# MOOSE/QPX Cross-Chat Bootstrap

**Status:** canonical entry point  
**Command:** `moose-test-init`  
**Purpose:** restore the minimum safe operating context and the current operational evidence baseline in a fresh chat without relying on prior-chat memory or preloading the complete rule inventory.

## Bootstrap contract

When the user sends `moose-test-init`, treat this file as the repository boot entry point.

The bootstrap must reconstruct operating state and current process evidence from canonical repository sources, not from remembered conversation text.

A successful bootstrap restores two distinct layers:

```text
RULE CONTEXT
  -> what procedure applies now

METRICS CONTEXT
  -> what the measured operating history currently says about efficiency, failure cost, and process hypotheses
```

Metrics observations inform operating decisions but do not override canonical rules, scientific validity, or closure-quality constraints.

## Bootstrap sequence

```text
1. resolve the current repository ref / working branch from explicit user or current-work evidence;
   do not silently substitute the default branch when an active working ref is known
2. read docs/operating_system/README.md to identify the current named operating-system baseline
3. read OPERATING_CORE.md
4. recover the active issue / bounded-work STATE and immediate resume obligation when one exists
5. read PROTOCOL_INDEX.md
6. read docs/protocols/rule_working_set.md
7. read docs/metrics/README.md and restore its required current METRICS CONTEXT
8. classify the immediate primary phase: PLAN / RESEARCH / IMPLEMENT / VALIDATE / CLOSE
9. activate only the selected phase owner(s)
10. add MUTATE, SCIENTIFIC_EXECUTION, or temporary diagnostic material only when triggered
11. consult docs/rules/INVENTORY.md only when the required dormant owner is unclear or expansion is triggered
12. report the reconstructed operating state and material metrics context
```

The named operating-system baseline is descriptive/versioning state. Its historical log must not replace or override the live canonical operating documents.

## Metrics bootstrap contract

`docs/metrics/README.md` is the one entry point for metrics loading. Follow its current bootstrap list rather than duplicating metric-file selection rules here.

At minimum, initialization must become aware of:

```text
current issue-efficiency baseline / latest monitored trend
latest efficiency or batching observation when available
latest incident/root-cause observation
material current process bottleneck or improvement hypothesis
important evidence limitations when values are reconstructed or unavailable
```

The purpose is data-driven operating-system improvement. Planning decisions such as Issue/work-batch sizing, validation consolidation, preflight investment, gate hardening, clarification reduction, and evidence reuse should use the available metrics rather than relying only on qualitative memory.

Do not preload every historical metrics snapshot. `docs/metrics/README.md` defines the compact current set and when historical expansion is justified.

## Minimum initialization report

A successful bootstrap should report, when the information is available:

```text
Operating system version
Repository / ref
Active work item or issue
Immediate resume obligation
Primary phase
Active core/phase packs
Temporary or auxiliary packs
Material unresolved hold/blocker
Metrics context: current efficiency trend / latest relevant snapshot
Metrics context: material incident or process bottleneck
Metrics context: current process hypothesis to preserve/test when relevant
```

Do not claim initialization is complete if the current work state, immediate resume obligation, or required metrics context is unresolved.

## Working-set rule

`moose-test-init` is not a command to load every potentially useful protocol or every historical measurement.

The initial rule working set remains:

```text
CORE
+ one primary PHASE PACK
+ only immediately triggered auxiliary/temporary material
```

The METRICS CONTEXT is an observation layer, not an additional rule pack, and therefore does not justify permanent rule accumulation.

After initialization, every new user turn is a rule-set re-evaluation event. Reassess the current phase, newly observed evidence, symptoms, unresolved obligations, and any material metrics signal; load newly triggered rule material and unload material that is no longer relevant according to `docs/protocols/rule_working_set.md`.

## Cross-chat authority

Fresh chats should not depend on another chat's private reasoning or historical wording to understand the operating system. Durable authority is:

```text
BOOTSTRAP.md                       -> cross-chat entry point
docs/operating_system/README.md    -> current named OS baseline / version-log index
OPERATING_CORE.md                  -> always-active invariants
PROTOCOL_INDEX.md                  -> routing / phase selection
docs/protocols/rule_working_set.md -> load / unload policy
docs/metrics/README.md             -> current metrics-context entry point
docs/rules/INVENTORY.md            -> dormant owner locator
active issue/body                   -> current STATE
phase protocol                      -> current technical procedure
```

Version snapshots under `docs/operating_system/versions/` and metrics snapshots under `docs/metrics/**/snapshots/` are historical/comparative evidence. Conversation history may help locate the current work item, but neither history nor a snapshot overrides the live canonical sources.

## Failure handling

If bootstrap selects the wrong phase, misses a required rule owner, misses material current metrics evidence, or activates irrelevant material that contributes to an operating error, treat that as routing/working-set/bootstrap evidence. Record it through the incident-learning system when material rather than compensating by permanently loading more rules or every historical metrics file.
