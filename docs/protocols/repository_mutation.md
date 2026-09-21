# Repository Mutation Policy Overlay

**Status:** consumer-local policy under Paul  
**Purpose:** define MOOSE/Physics authorization and evidence-lineage meaning while delegating deterministic mutation mechanics to the central Paul `repository-mutation` skill.

## Central mechanic

For supported portable mutations:

```text
file create/update/delete
branch create
```

use the exact central contract/action declared in:

```text
docs/operating_system/central_skills.json
.github/workflows/refactor.yml
```

The central skill owns target identity checks, stale-SHA handling, retry-safe desired-state recognition, validation-gate enumeration, and post-write verification.

Do not recreate those mechanics here.

## Local policy owner

`.chatgpt-operation.json` owns consumer authorization:

- repository binding;
- allowed/denied file paths;
- allowed/denied branch names;
- allowed portable actions;
- local validation-gate workflow names.

Paul ER-03/ER-05/ER-07/ER-08 remain applicable.

## RM-L01 — Semantic intent

Before mutation, the owning issue/work item must establish what semantic state should change and what scope must remain unchanged.

A central mutation PASS proves repository mutation mechanics, not Physics correctness or issue acceptance.

## RM-L02 — Evidence-lineage meaning

This repository owns whether a pending validation lineage is:

```text
GLOBAL
SCOPED
NONE
```

and which Physics resources/dependencies conflict with it.

Generic controller liveness classification is delegated to central controller skills; Physics dependency/scientific meaning stays local.

## RM-L03 — Unsupported mutation surfaces

Portable v1 does not own branch move/delete, issue/PR mutation, Git-object snapshot construction, or other unsupported resource classes.

Those actions require an explicitly appropriate safe mutator and current target evidence under Paul essential rules.

Do not emulate an unsupported action through a misleading supported manifest.

## RM-L04 — History and destructive actions

Force/history rewriting is not authorized by default.

A destructive or history-affecting action requires exact target identity and explicit authority appropriate to the work item.

## RM-L05 — Validation meaning

Workflow/checker failure must be classified by the actual validation layer.

Repository-operation failure does not automatically establish scientific failure. Physics P0-P3 meaning remains owned by `docs/protocols/validation.md`.

## RM-L06 — Dependency synchronization

When a lifecycle/dependency mutation changes current canonical state, update directly dependent live state that would otherwise become contradictory.

Do not rewrite historical evidence or archives merely because current state changed.

## RM-L07 — No probe pollution

Do not create canonical files, commits, refs, issues, or comments merely to test whether a mutator works.

Tool capability is established through schema/discovery/read operations and validated central mechanics.

## Completion

Repository synchronization is complete when the intended live state is verified, dependent current state is coherent, and any required exact-head validation is resolved under its owning local acceptance semantics.

The objective is correct canonical state with the smallest consumer-local policy layer.
