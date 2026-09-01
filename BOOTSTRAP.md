# MOOSE/QPX Cross-Chat Bootstrap

**Status:** canonical entry point  
**Command:** `moose-test-init`  
**Purpose:** restore the minimum safe operating context in a fresh chat without relying on prior-chat memory or preloading the complete rule inventory.

## Bootstrap contract

When the user sends `moose-test-init`, treat this file as the repository boot entry point.

The bootstrap must reconstruct operating state from canonical repository sources, not from remembered conversation text.

## Bootstrap sequence

```text
1. resolve the current repository ref / working branch from explicit user or current-work evidence;
   do not silently substitute the default branch when an active working ref is known
2. read OPERATING_CORE.md
3. recover the active issue / bounded-work STATE and immediate resume obligation when one exists
4. read PROTOCOL_INDEX.md
5. read docs/protocols/rule_working_set.md
6. classify the immediate primary phase: PLAN / RESEARCH / IMPLEMENT / VALIDATE / CLOSE
7. activate only the selected phase owner(s)
8. add MUTATE, SCIENTIFIC_EXECUTION, or temporary diagnostic material only when triggered
9. consult docs/rules/INVENTORY.md only when the required dormant owner is unclear or expansion is triggered
10. report the reconstructed operating state
```

## Minimum initialization report

A successful bootstrap should report, when the information is available:

```text
Repository / ref
Active work item or issue
Immediate resume obligation
Primary phase
Active core/phase packs
Temporary or auxiliary packs
Material unresolved hold/blocker
```

Do not claim initialization is complete if the current work state or immediate resume obligation is required but unresolved.

## Working-set rule

`moose-test-init` is not a command to load every potentially useful protocol.

The initial working set is:

```text
CORE
+ one primary PHASE PACK
+ only immediately triggered auxiliary/temporary material
```

After initialization, every new user turn is a rule-set re-evaluation event. Reassess the current phase, newly observed evidence, symptoms, and unresolved obligations; load newly triggered material and unload material that is no longer relevant according to `docs/protocols/rule_working_set.md`.

## Cross-chat authority

Fresh chats should not depend on another chat's private reasoning or historical wording to understand the operating system. Durable authority is:

```text
BOOTSTRAP.md                       -> cross-chat entry point
OPERATING_CORE.md                  -> always-active invariants
PROTOCOL_INDEX.md                  -> routing / phase selection
docs/protocols/rule_working_set.md -> load / unload policy
docs/rules/INVENTORY.md            -> dormant owner locator
active issue/body                   -> current STATE
phase protocol                      -> current technical procedure
```

Conversation history may help locate the current work item, but it does not override these canonical sources.

## Failure handling

If bootstrap selects the wrong phase, misses a required rule owner, or activates irrelevant material that contributes to an operating error, treat that as routing/working-set evidence. Record it through the incident-learning system when material rather than compensating by permanently loading more rules.