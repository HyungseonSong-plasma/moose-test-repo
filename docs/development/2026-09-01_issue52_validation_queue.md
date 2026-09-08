# Issue52 staged validation queue

**Work ID:** `qpx-stats-mapping-consolidation-retirement`  
**Issue:** #52  
**Protocol:** `docs/protocols/coding.md` / CODE-13  
**Status:** READY FOR ISSUE CLOSE / V0-V5 PASS / NO RETIREMENT CANDIDATES

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
               ↓ V5 PASS
       thin-bridge checkpoint
               ↓
   retirement candidates = 0
               ↓
       READY FOR ISSUE CLOSE
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
- interpretation: the `99` total included the new canonical `build_jacobian_accuracy_stats` helper and therefore was not a valid bridge-only comparison. M5 corrected the metric by separating canonical and producer ownership.
- status: `PASS`

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
- accepted evidence:
  - `ISSUE52_STATS_INVENTORY: PASS`
  - `ISSUE52_STATS_PRODUCER_BRIDGE_LOC: 87`
  - `ISSUE52_STATS_CANONICAL_HELPER_LOC: 12`
  - `ISSUE52_STATS_RETIREMENT_CANDIDATE_COUNT: 0`
  - `producer_accuracy_callers: []`
  - `parse_failures: []`
  - Issue45 bridge LOC: `42`
  - Issue46 bridge LOC: `38`
  - PF1 bridge LOC: `7`
- semantic ownership proof:
  - Issue45 retains KSP/termination/true-residual/variable-residual/scaling fact selection;
  - Issue46 retains thresholded/localized matrix-comparison construction;
  - PF1 retains work-counter-to-Convergence selection.
- caller/import proof:
  - each bridge has an in-module caller;
  - no bridge is compatibility-only;
  - no producer directly calls `build_accuracy_stats` after migration.
- status: `PASS`

## Thin-bridge / retirement decision

No deletion cut is authorized or required.

All three producer bridges retain non-zero semantic ownership:

```text
build_first_linear_stats
  -> Issue45 convergence fact-selection owner

build_jacobian_localization_stats
  -> Issue46 localized matrix-comparison owner

build_measurement_stats
  -> PF1 work-counter convergence-selection owner
```

The retirement proof therefore correctly returns zero candidates. Removing any
of these helpers solely to reduce LOC would collapse producer-specific semantics
back into a generic layer and violate the Issue52 acceptance boundary.

## Measured result

```text
producer bridge LOC:        93 -> 87   (-6)
canonical Jacobian helper:   0 -> 12   (+12)
producer direct Accuracy mapping owners: 2 -> 0
canonical shared Jacobian Accuracy owner: 0 -> 1
retirement candidates:      0
```

The relevant success criterion is ownership reduction rather than forced net
repository LOC reduction. Shared Jacobian mapping is now canonical while all
remaining producer bridges have explicit non-zero semantic ownership.

## Closure readiness

All applicable Issue52 validation obligations are discharged:

- semantic-identity-selected Jacobian consolidation: PASS;
- Issue45 migration: PASS;
- Issue46 migration: PASS;
- Stats builder integration: PASS;
- full QPX harness: PASS;
- branch-local AST inventory: PASS;
- ownership-aware retirement proof: PASS;
- convergence over-consolidation rejected as `NOT_COMMON`;
- deletion candidates: none.

No additional local validation or deletion work is required before the issue
state is synchronized to `CLOSED / PASS` in a separate issue-only mutation phase.
