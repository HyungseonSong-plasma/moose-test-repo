# MOOSE/QPX Test Workspace

This repository is the operating and regression workspace for MOOSE/QPX plasma-simulation development.

## Operating boundary

Use `OPERATING_CORE.md` for always-active invariants and `PROTOCOL_INDEX.md` for deterministic procedure routing. Current technical state is owned by the active GitHub issue body; issue comments are historical evidence.

For multi-issue capability delivery, use `docs/protocols/milestone_delivery.md`.

## Delivery model

Non-trivial development is organized hierarchically:

```text
Project / Architecture Goal
  -> Milestone
    -> Issue
      -> Work Batch
        -> Atomic Mutation / Validation Unit
```

The boundaries are intentionally distinct:

```text
Project    = strategic objective
Milestone  = usable capability delivery boundary
Issue      = semantic implementation and rollback boundary
Work Batch = execution-efficiency boundary
Mutation   = repository safety boundary
```

A milestone begins with M0 capability/DAG planning, proceeds through independently accepted issues, and closes only after a milestone integration guard and capability-level acceptance. Issue-local validation evidence is reused at milestone closure when still current; milestone validation focuses on cross-issue integration plus the declared regression safety net.

## Current development focus

Architecture track:

```text
#53 CLOSED/PASS  stats-builder decomposition
#54 CLOSED/PASS  Issue45 owner decomposition
#55 CLOSED/PASS  large-owner decomposition
#56 CLOSED/PASS  next-owner decomposition
#57 CLOSED/PASS  Stage A/B large-owner consolidation
#58 ACTIVE       declarative ExperimentSpec architecture
```

Issue #58 is the current architecture migration: move case-specific data and declarative transforms from Python recipes into typed experiment specifications while keeping algorithms/runtime capabilities in reusable Python owners.

Scientific investigation remains a separate evidence track and must not be advanced or consume EVR/P3 evidence merely to validate architecture/refactor work.

## Validation model

Runtime canonical evidence comes from the user-local real `qpx-opt`. GitHub Actions and static checks are supporting evidence. Technical validation follows P0 -> P1 -> P2 -> P3 and the bounded EVR workflow defined in the protocol documents.

Architecture/refactor work should prefer static, characterization, import/contract, and consolidated harness validation. Scientific runtime evidence is consumed only when the scientific closure claim requires it and the relevant work explicitly authorizes it.

## Repository role

This workspace stores regression inputs, minimal reproducers, checkers/reference data, incident/development logs, scripts, specifications, and small source deltas needed to reproduce or document MOOSE/QPX investigations. Production source changes belong in the appropriate source repository.