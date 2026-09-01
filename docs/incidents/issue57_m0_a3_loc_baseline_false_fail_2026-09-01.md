# Issue57 M0 A3 LOC baseline false FAIL — 2026-09-01

## Summary

Issue57 consolidated local validation produced a single M0 inventory failure for A3 (`qpx_harness/issue46_jacobian_localization.py`):

```text
ISSUE57_M0_TARGET: FAIL A3 decision=KEEP_COHESIVE baseline_loc=698 current_loc=729 current_sha=a39d914330ec43da3612910b83c53e167f921b7c
ISSUE57_M0_INVENTORY: FAIL
```

The same validation batch showed:

```text
ISSUE57_FINAL_UNCHANGED: PASS A3_jacobian_localization observed=a39d914330ec43da3612910b83c53e167f921b7c expected=a39d914330ec43da3612910b83c53e167f921b7c
ISSUE57_FINAL_GUARD: PASS
ISSUE46_JAC_LOCALIZATION_STATS_MAPPING_SELFTEST: PASS
ISSUE46_JAC_LOCALIZATION_SELFTEST: PASS
ISSUE46_JAC_LOCALIZATION_RUNTIME_SELFTEST: PASS
QPX_HARNESS_SELFTEST: PASS
```

## Root cause

The A3 Git blob SHA was unchanged and exactly matched the frozen baseline. The M0 gate nevertheless compared the current physical LOC against an incorrectly recorded baseline value of `698`. The actual physical LOC for the frozen blob is `729`.

This is a validator baseline-data defect, not a production-code drift and not a scientific/runtime failure.

## Classification

- MET-20 learning status: `GATE_DEFECT`
- Owning phase: `VALIDATE / TEMPORARY INCIDENT-LEARNING`
- Gate invoked: yes
- Detection stage: consolidated user-local validation
- EPR required: no
- Enforcement decision: `REPAIR_GATE_AND_SELFTEST`
- Production-code impact: none
- Scientific EVR consumed: 0

## Repair

`tests/Issue57_stage_ab_large_owner/inventory.py` was corrected so A3 freezes the exact tuple:

```text
blob = a39d914330ec43da3612910b83c53e167f921b7c
physical LOC = 729
decision = KEEP_COHESIVE
```

The repair changes only gate metadata. No Issue31/43/45/46 production owner, CLI, recipe, physics, numerical setting, evidence schema, or runtime path is changed.

## Validation disposition

Because the original consolidated batch already passed the final structural guard and all relevant owner/unified self-tests, only the repaired M0 inventory requires rerun. Re-running the full scientific/runtime or self-test batch would add no decision-changing evidence.

Expected repaired terminal marker:

```text
ISSUE57_M0_TARGET: PASS A3 decision=KEEP_COHESIVE baseline_loc=729 current_loc=729 current_sha=a39d914330ec43da3612910b83c53e167f921b7c
ISSUE57_M0_INVENTORY: PASS
```

Issue57 remains open until that repaired gate is observed PASS.
