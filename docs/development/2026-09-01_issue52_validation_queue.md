# Issue52 staged validation queue

**Work ID:** `qpx-stats-mapping-consolidation-retirement`  
**Issue:** #52  
**Protocol:** `docs/protocols/coding.md` / CODE-13  
**Status:** ACTIVE / V0-V4 PASS / THIN-BRIDGE + RETIREMENT PROOF GATE ACTIVE

## Dependency graph

```text
M0 AST inventory/proof harness
        ↓ V0 PASS
M1 shared Jacobian->Accuracy owner
        ↓ V1 PASS
      /           \
M2 Issue45       M4 Issue46
migration         migration
  ↓ V2 PASS        ↓ V3 PASS
      \           /
       V4 integration PASS
               ↓
M5 ownership-aware inventory refinement
               ↓ V5
       thin-bridge checkpoint
               ↓
       zero-caller proof
               ↓
      retirement/deletion cuts
```

M2 and M4 are siblings. Both depend on M1, but neither depends on the other.

## Accepted validation evidence

### V0 — branch-local Stats mapping inventory

- modification: `M0`
- commit: `639bc132a31be430b749ff549ca0498cd576e018`
- observed:
  - `ISSUE52_STATS_INVENTORY: PASS`
  - pre-refactor producer bridge LOC baseline: `93`
  - Issue45 `44`, Issue46 `42`, PF1 `7`
  - parse failures: `[]`
  - direct producer `build_accuracy_stats` callers: Issue45 + Issue46
- status: `PASS`

### V1 — shared Jacobian Accuracy owner

- modification: `M1`
- commit: `b68f6fc691ab017f8ebfc8ed55c2ec1eccfdc570`
- path: `qpx_harness/analysis/metrics/accuracy.py`
- accepted marker: `QPX_JACOBIAN_ACCURACY_MAPPING_SELFTEST: PASS`
- status: `PASS`

### V2 — Issue45 migration

- modification: `M2`
- commit: `10f3cfe2260594e359866d4f6cf5d529d941ec28`
- preserved ownership: KSP identity, termination, true residual, variable residual, scaling-factor selection
- accepted markers:
  - `ISSUE45_FIRST_LINEAR_STATS_MAPPING_SELFTEST: PASS`
  - `ISSUE45_FIRST_LINEAR_SELFTEST: PASS`
- status: `PASS`

### V3 — Issue46 migration

- modification: `M4`
- commit: `a8a8367ef87ce3b9c4b816903553f96b6b712a8d`
- preserved ownership: thresholded difference extraction, localization mapping, matrix blocks/counts/L2
- accepted markers:
  - `ISSUE46_JAC_LOCALIZATION_STATS_MAPPING_SELFTEST: PASS`
  - `ISSUE46_JAC_LOCALIZATION_SELFTEST: PASS`
  - `ISSUE46_JAC_LOCALIZATION_RUNTIME_SELFTEST: PASS`
- status: `PASS`

### V4 — integration

- accepted markers:
  - `QPX_STATS_BUILDER_SELFTEST: PASS`
  - `QPX_HARNESS_SELFTEST: PASS`
  - `ISSUE52_STATS_INVENTORY: PASS`
  - `ISSUE52_VALIDATION_QUEUE: PASS`
- post-migration raw helper total reported by the first inventory version: `99`
- interpretation: the `99` total is not a valid bridge-only comparison because it includes the new canonical `build_jacobian_accuracy_stats` helper. The bridge metric therefore requires ownership-aware reclassification before any deletion decision.
- status: `PASS / METRIC REFINEMENT REQUIRED`

## M2 common Convergence candidate classification

The planned common solver/Convergence consolidation is `NOT_COMMON` at this stage.

Evidence:

```text
PF1:
  work counters -> ConvergenceStats

Issue45:
  first-linear termination
  KSP/PC/restart identity
  true residual trajectory
  variable residual blocks
  scaling-factor blocks
  -> ConvergenceStats
```

The producers share the canonical `build_convergence_stats` constructor but do
not share the same fact-selection semantics. No additional convergence helper is
authorized merely to reduce textual size.

## V5 — ownership-aware thin-bridge / retirement proof

- modification: `M5`
- commit: `7651570fceca4f491d8d3a47cb39dbdec1c6d363`
- path: `tests/Issue52_stats_mapping_consolidation/inventory.py`
- purpose:
  - separate canonical helper LOC from producer bridge LOC;
  - prove direct producer calls to `build_accuracy_stats` are zero;
  - inventory bridge call/import sites;
  - require explicit semantic-ownership classification for every producer bridge;
  - emit retirement candidates only when semantic ownership is empty and caller/import proof permits retirement.
- command:

```bash
python3 tests/Issue52_stats_mapping_consolidation/inventory.py
```

- required markers:
  - `ISSUE52_STATS_INVENTORY: PASS`
  - `ISSUE52_STATS_PRODUCER_BRIDGE_LOC: ...`
  - `ISSUE52_STATS_CANONICAL_HELPER_LOC: ...`
  - `ISSUE52_STATS_RETIREMENT_CANDIDATE_COUNT: ...`
- expected producer-bridge comparison if source shape is preserved:
  - before: `93`
  - after shared Jacobian migration: `87` (`42 + 38 + 7`)
- status: `PENDING`

## Retirement boundary

No bridge/helper deletion is authorized until V5 returns concrete branch-local
evidence. A bridge may be deleted only when all of these are true:

```text
semantic ownership == zero
compatibility responsibility == zero
canonical replacement exists
AST/direct caller proof permits retirement
import compatibility proof permits retirement
```

Current explicit semantic-ownership expectations:

- Issue45 bridge: non-zero — detailed Convergence fact selection remains.
- Issue46 bridge: non-zero — localized matrix-comparison construction remains.
- PF1 bridge: non-zero — PF1 work-counter-to-Convergence selection remains.

If V5 confirms these expectations and returns zero retirement candidates, the
correct result is to retain the bridges and report ownership reduction without a
forced deletion. If V5 exposes a genuine zero-ownership candidate, retire only
that target in a separate small cut with immediate validation.
