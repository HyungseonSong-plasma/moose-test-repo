# Central Operational Skill Bootstrap

**Status:** canonical consumer load manifest  
**Owner:** `moose-test-init` consumer policy  
**Central source:** `HyungseonSong-plasma/chatgpt-operation`

This file defines the consumer-side loading semantics. The machine-readable source of truth for names, revisions, paths, triggers, and expected blob SHAs is `docs/operating_system/central_skills.json`. This file does not duplicate the central skill contracts locally.

## Core skill load set

A successful `moose-test-init` must fetch and read each of these files from the exact immutable revision before local phase routing is considered complete:

| Skill | Exact central revision | Contract path | Load mode |
|---|---|---|---|
| controller-lifecycle | `ab9091e2eb2e1f186110a0afc5b1da4479349e1b` | `skills/controller-lifecycle/README.md` | ALWAYS |
| controller-throughput | `ab9091e2eb2e1f186110a0afc5b1da4479349e1b` | `skills/controller-throughput/README.md` | ALWAYS |
| state-refresh | `ab9091e2eb2e1f186110a0afc5b1da4479349e1b` | `skills/state-refresh/README.md` | ALWAYS |

These are operational contracts, not local repository rules. They govern portable controller lifecycle, work-burst/liveness classification, and deterministic refresh planning.

## Trigger-loaded skill set

Load these contracts only when their local trigger is active:

| Trigger | Skill | Exact central revision | Contract path |
|---|---|---|---|
| actual repository mutation / MUTATE pack | repository-mutation | `661ca7fe3b214e9ca8ac802d517fa1e40f65ecca` | `skills/repository-mutation/README.md` |
| governed experiment/refactor manifest execution | governed-work | `4d5683b12be31e28b44bbe34723b02ae3493b172` | `skills/governed-work/README.md` |

The contract revision must match the executable central action revision used by this repository. Do not load a different documentation revision and then execute an older pinned action as if they were the same contract.

## Deterministic load procedure

Read `central_skills.json` first. For each required skill entry:

```text
1. resolve the exact central repository revision from this manifest;
2. fetch the declared contract path from that exact revision;
3. verify that the fetched source is from the declared repository/ref/path and that its blob SHA matches `expected_blob_sha`;
4. read the contract before applying the skill;
5. record the loaded skill name + exact revision in the initialization state;
6. never substitute central main/latest for the exact pin;
7. never reconstruct the skill from conversation memory or a local copy.
```

A local `skills/` tree or `src/chatgpt_operation` package is not an acceptable substitute.

## Failure semantics

If an ALWAYS skill cannot be retrieved or its exact revision/path cannot be established:

```text
CENTRAL_SKILL_LOAD = BLOCKED
INITIALIZATION_COMPLETE = false
```

Do not silently continue under remembered or locally reconstructed controller mechanics.

If a trigger-loaded skill cannot be retrieved when its trigger becomes active, block that triggered operation only; do not reinterpret the failure as scientific or Physics-domain failure.

## Ownership boundary

```text
chatgpt-operation
  -> portable operational skill contracts and deterministic evaluators/actions

moose-test-repo
  -> Physics/science semantics, dependency graph, phase routing,
     repository-specific surface mappings, local authorization,
     validation/scientific interpretation
```

Loading a central skill does not transfer Physics/scientific ownership to the central repository.

## Initialization reporting

The minimum initialization report must include a compact central-skill line, for example:

```text
Central skills:
  controller-lifecycle@ab9091e...
  controller-throughput@ab9091e...
  state-refresh@ab9091e...
Triggered central skills:
  <none | explicit skill@revision>
```
