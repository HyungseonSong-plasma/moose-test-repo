# MOOSE/Physics Test Workspace

This repository is the operating and regression workspace for MOOSE/Physics plasma-simulation development.

## Operating boundary

Use `OPERATING_CORE.md` for always-active invariants and `PROTOCOL_INDEX.md` for deterministic procedure routing. Current technical state is owned by the active GitHub issue or bounded work item; comments are historical evidence unless the canonical state says otherwise.

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

A milestone begins with capability/DAG planning, proceeds through independently accepted issues, and closes only after a milestone integration guard and capability-level acceptance. Issue-local validation evidence is reused at milestone closure when still current; milestone validation focuses on cross-issue integration plus the declared regression safety net.

## Validation model

GitHub Actions and static checks provide construction and regression evidence. Scientific runtime claims require the canonical real-runtime evidence defined by the operating protocols; CI success or failure alone must not be promoted to a scientific PASS or FAIL.

Architecture and refactor work should prefer static, characterization, import/contract, and consolidated harness validation. Scientific runtime evidence is consumed only when the scientific closure claim requires it and the relevant work explicitly authorizes it.

## Repository role

This workspace stores regression inputs, minimal reproducers, checkers/reference data, incident/development logs, scripts, specifications, and small source deltas needed to reproduce or document MOOSE/Physics investigations. Production source changes belong in the appropriate source repository.

## Legacy compatibility surfaces

Repository-local project naming uses `Physics` / `physics`. Legacy `QPX` / `qpx` identifiers may remain only where they identify an external dependency, an already-published immutable artifact, or another compatibility surface that cannot be renamed without changing the referenced object. Such compatibility identifiers are not the canonical repository namespace.

## License

Unless otherwise noted, repository-authored content is licensed under the Apache License 2.0. Commercial use, modification, redistribution, private use, and use within proprietary products are permitted subject to the license terms.

Components that carry their own license remain governed by that license. In particular, `physics_app/LICENSE` currently contains GNU LGPL 2.1 terms and is not overridden by the repository-level Apache-2.0 license. External dependencies including MOOSE, PETSc, Crane, Squirrel, Zapdos, and their transitive dependencies retain their respective upstream licenses.
