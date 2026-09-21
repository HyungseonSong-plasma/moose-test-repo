# Issue #50 staged validation queue — 2026-09-01

**Status:** ACTIVE / deferred validation queue  
**Work:** #50 common-mapping consolidation  
**Protocol owner:** `docs/protocols/coding.md` / CODE-13

This log records the currently deferred local validations for the Stats consolidation batch. The purpose is to reduce repeated user-local validation rounds while keeping every cut causally attributable and rollbackable.

## Queue

| Validation | Modification / commit | Semantic scope | Validation claim | Dependency / rollback boundary | Status |
|---|---|---|---|---|---|
| V1 | `74de08eabda16cd18d32346ba94b96423f928876` | add canonical `build_runtime_common_stats()` | shared issue-runtime `case_id` / `returncode` / `wall_seconds` maps to `CommonStats` without changing existing result-record paths | root of runtime-common consolidation; if V1 fails, discard all later cuts that depend on this helper | PENDING |
| V2 | `83ce953475916f48a9fbc38d384e4c2b1336e13c` | add canonical `build_runtime_simulation_stats()` | runtime-common mapping composes into `SimulationStats` with no invented efficiency facts | depends on V1; if V2 fails, caller migrations depending on this helper are untrusted | PENDING |
| V3 | `2eefdb07d63403d6c338be2be50d12a07d761be2` | rewire Issue45 first-linear Stats bridge to canonical runtime SimulationStats builder | Issue45 Common/Convergence/Accuracy mapping remains semantically identical and policy/evidence remain outside Stats | depends on V1/V2 | PENDING |
| V4 | `f69446ec0be377338c0feb76587f5efed5618a81` + repair `f92cb51f8a65dd26d22f917f6ff5fd9fb6efb9b9` | rewire Issue46 localization Stats bridge to canonical runtime SimulationStats builder while restoring unrelated structural failure classifier | Issue46 Common/Accuracy mapping remains identical, no convergence facts are invented, and pre-existing structural classifier is preserved | depends on V1/V2; sibling of Issue45 rewiring rather than semantically dependent on V3 | PENDING |

## Incident note

The first Issue46 rewiring commit accidentally changed `MOOSE_CONSTRAINT_CONTROL_STRUCTURE_FAIL` to `MOOSE_CONSTRAINT_CONTROL_FAIL`. Post-write verification detected the unrelated semantic drift and commit `f92cb51f8a65dd26d22f917f6ff5fd9fb6efb9b9` restored the original classifier.

Canonical incident evidence:

`docs/incidents/issue46_stats_migration_semantic_drift_2026-09-01.md`

V4 therefore validates the repaired net state, not the transient incorrect state.

## Planned discharge order

```text
V1
  -> focused runtime-common characterization
V2
  -> focused runtime-SimulationStats characterization
V3
  -> Issue45 Stats mapping/module self-test
V4
  -> Issue46 Stats mapping/module self-test
final batch gate
  -> qpx_harness Stats Builder self-test + scripts/qpx.py self-test
```

Where practical, V1/V2 characterization should be incorporated into the canonical Stats Builder self-test before the queue is discharged so the user does not need separate ad-hoc validation commands.

## Rollback semantics

- V1 FAIL: V2 and both caller rewiring cuts are untrusted; remove dependent descendant changes before repairing the runtime-common boundary.
- V2 FAIL with V1 PASS: both caller rewiring cuts are untrusted; preserve the accepted V1 helper.
- V3 FAIL with V1/V2 PASS: roll back/repair Issue45 rewiring. Issue46 may remain because it is a sibling consumer of V2, not a semantic descendant of Issue45.
- V4 FAIL with V1/V2 PASS: roll back/repair Issue46 rewiring while preserving accepted V1/V2 and any independently accepted Issue45 cut.

No queued item may be promoted to accepted issue evidence until its validation is discharged. Issue closure/canonical retirement still requires the final validation gates defined by `validation.md`.
