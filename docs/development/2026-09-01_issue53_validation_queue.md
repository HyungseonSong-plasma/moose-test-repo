# Issue53 staged validation queue

**Work ID:** `qpx-stats-builder-decomposition`  
**Issue:** #53  
**Protocol:** `docs/protocols/coding.md` / CODE-13  
**Status:** ACTIVE / D1 PASS / D2 PASS / D3 ACCURACY OWNER STAGED / LOCAL DIAGNOSTIC GATE READY

## Local execution contract

Local workspaces are disposable ZIP snapshots of the GitHub canonical repository.
Local commands are diagnostics only.

```text
NO local git commands
NO local cp/rm/mv commands
NO local source mutation commands
```

Repository mutations are performed against GitHub canonical state separately.
Local evidence is used only to validate the current downloaded snapshot.

## Accepted baseline and D1

```text
baseline stats_builder.py: 942 LOC
embedded self_test:         198 LOC

V0 inventory:               PASS
V0.5 coercion helper:       PASS
V1 Efficiency shadow:       PASS
V2 Convergence shadow:      PASS

D1 Efficiency extraction:  PASS
stats_builder.py after D1:  836 LOC
```

D1 user-local evidence included:

```text
ISSUE53_STRUCTURAL_GUARD_D1: PASS
ISSUE53_STRUCTURAL_GUARD_LOC: 836
QPX_EFFICIENCY_STATS_MAPPING_SELFTEST: PASS
ISSUE53_D1_REEXPORT: PASS
QPX_STATS_BUILDER_SELFTEST: PASS
PF1_STATS_MAPPING_SELFTEST: PASS
QPX_HARNESS_SELFTEST: PASS
ISSUE53_DECOMPOSITION_STAGE: D1_EFFICIENCY_EXTRACTED
```

Historical D1 incidents remain recorded under:

```text
docs/incidents/issue53_efficiency_extraction_transcription_drift_2026-09-01.md
docs/incidents/issue53_inventory_stage_blind_false_fail_2026-09-01.md
```

## D2 — Convergence extraction

D2 moved the Convergence mapping implementation from `stats_builder.py` to:

```text
qpx_harness/analysis/metrics/convergence.py
```

`stats_builder.build_convergence_stats` remains available through a compatibility re-export.

User-local D2 evidence:

```text
ISSUE53_D2_MIGRATOR_PREFLIGHT: PASS
ISSUE53_D2_MIGRATOR_GIT_DEPENDENCY: NONE
ISSUE53_D2_MIGRATOR_BEFORE_LOC: 836
ISSUE53_D2_MIGRATOR_AFTER_LOC: 653
ISSUE53_D2_MIGRATOR_REMOVED_LOC: 183
ISSUE53_STRUCTURAL_GUARD_D2: PASS
ISSUE53_STRUCTURAL_GUARD_LOC: 653
QPX_CONVERGENCE_STATS_MAPPING_SELFTEST: PASS
ISSUE53_D2_REEXPORT: PASS
ISSUE45_FIRST_LINEAR_STATS_MAPPING_SELFTEST: PASS
ISSUE45_FIRST_LINEAR_SELFTEST: PASS
PF1_STATS_MAPPING_SELFTEST: PASS
QPX_STATS_BUILDER_SELFTEST: PASS
QPX_HARNESS_SELFTEST: PASS
ISSUE53_DECOMPOSITION_INVENTORY: PASS
ISSUE53_STATS_BUILDER_LOC: 653
ISSUE53_DECOMPOSITION_STAGE: D2_CONVERGENCE_EXTRACTED
ISSUE53_D2_CODES: 0 0 0 0 0 0 0 0 0
ISSUE53_D2_LOCAL_GATE: PASS
```

GitHub canonical was synchronized to the same validated structural fingerprint:

```text
stats_builder.py LOC:                 653
_error_from_mapping line:             196
build_simulation_stats line:          419
self_test line:                       452
```

D2 status: `PASS`.

## D3 — Accuracy ownership inversion

Current staged owner commit:

```text
52de815e070dcb28e773cf415ed2dd26f718b6e9
refactor(issue53): make AccuracyStats mapping locally owned
```

`qpx_harness/analysis/metrics/accuracy.py` now owns:

```text
_error_from_mapping
_matrix_blocks
_matrix_entries
build_accuracy_stats
build_jacobian_accuracy_stats
```

The previous reverse dependency:

```text
metrics/accuracy.py -> stats_builder.build_accuracy_stats
```

has been removed.

`stats_builder.py` still retains its existing Accuracy implementation at this stage.
D3 destructive removal is blocked until the staged owner passes local diagnostics.

### VD3A — Accuracy owner diagnostic gate

Run on a freshly downloaded GitHub ZIP snapshot:

```bash
python3 -m qpx_harness.analysis.metrics.accuracy
python3 -m qpx_harness.issue45_first_linear --self-test
python3 -m qpx_harness.issue46_jacobian_localization --self-test
python3 -m qpx_harness.analysis.stats_builder
python3 scripts/qpx.py self-test
python3 tests/Issue53_stats_builder_decomposition/inventory.py
```

Required evidence:

```text
QPX_ACCURACY_STATS_MAPPING_SELFTEST: PASS
ISSUE45_FIRST_LINEAR_STATS_MAPPING_SELFTEST: PASS
ISSUE45_FIRST_LINEAR_SELFTEST: PASS
ISSUE46_JAC_LOCALIZATION_STATS_MAPPING_SELFTEST: PASS
ISSUE46_JAC_LOCALIZATION_SELFTEST: PASS
QPX_STATS_BUILDER_SELFTEST: PASS
QPX_HARNESS_SELFTEST: PASS
ISSUE53_DECOMPOSITION_INVENTORY: PASS
ISSUE53_STATS_BUILDER_LOC: 653
ISSUE53_DECOMPOSITION_STAGE: D2_CONVERGENCE_EXTRACTED
```

If VD3A passes, the next GitHub canonical cut is:

```text
D3 Accuracy local implementation removed from stats_builder.py
-> build_accuracy_stats re-exported from metrics/accuracy.py
-> expected stats_builder.py reduction by roughly 220 LOC
-> immediate read-back structural verification
-> fresh local diagnostics only
```

## Remaining target

After D3:

```text
Common/Environment owner extraction
embedded self_test extraction
thin composition facade
```

Final Issue53 acceptance target remains:

```text
stats_builder.py approximately 120-200 LOC
focused semantic owners
stable public facade behavior
full QPX P0 green
```
