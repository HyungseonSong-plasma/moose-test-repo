# Incident: wrong-action placeholder Issue #65 during Issue60/61 file phase

**Date:** 2026-09-01  
**Incident class:** repository mutation / wrong resource class / placeholder create  
**Scientific impact:** none  
**Business work interrupted:** #60 ExperimentSpec foundation and #61 transform registry

## Event

During a response explicitly locked to the **file** resource class, the intended work was to create new repository files for #60/#61. While navigating the GitHub tool surface, the assistant invoked `create_issue` with placeholder title `__noop__` instead of the planned file mutator.

Accidental live target:

```text
Issue #65
Title: __noop__
Initial state: OPEN
Milestone: none
Dependencies: none
```

This violated the existing prohibitions on placeholder/probe targets, resource-class mixing, mutation during tool-selection/discovery, and wrong-action mutation.

## Immediate repair

Under RM-09A the planned #60/#61 business mutations were stopped. Issue #65 was freshly read and then minimally repaired:

```text
Issue #65 -> CLOSED / NOT_PLANNED
body -> explicitly marks the issue as accidental and void
milestone -> none
dependencies -> none
```

The accidental issue cannot be deleted through the connected workflow, so preserving it as a closed/not-planned incident artifact is the minimal non-destructive repair.

## Root cause

The canonical protocol already bound resource class, action, target, payload shape, phase latch, and exact mutator. The remaining enforcement gap was **tool-schema surface contamination**: issue mutators had been loaded into a file-only mutation context, leaving an unrelated `create_issue` callable adjacent to the intended file operation.

The failure was therefore not ambiguity about the desired business action. It was failure to isolate the set of callable mutators before execution.

## Prevention

Strengthen `docs/protocols/repository_mutation.md` with a schema-surface isolation rule:

```text
resource class is frozen
  -> discover/load only mutators for that resource class
  -> if a wrong-resource mutator schema is loaded after the phase lock,
     business mutation permission for that response is revoked
  -> resume only in a fresh response with a clean resource-class tool surface
```

This converts resource-class isolation from a prose intent check into an earlier tool-availability boundary.

## Circuit-breaker result

```text
#60/#61 intended file mutations: NOT PERFORMED after incident
Issue #65 repair: VERIFIED CLOSED / NOT_PLANNED
scientific runtime/P3/EVR: NOT RUN
refactor EVR consumed: 0
```
