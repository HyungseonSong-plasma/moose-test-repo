# Issue52 staged validation queue

**Work ID:** `qpx-stats-mapping-consolidation-retirement`  
**Issue:** #52  
**Protocol:** `docs/protocols/coding.md` / CODE-13  
**Status:** ACTIVE / V0 PASS / M1 + M2 + M4 IMPLEMENTED / V1-V4 READY FOR ONE LOCAL DISCHARGE BATCH

## Dependency graph

```text
M0 AST inventory/proof harness
        ↓ V0 PASS
M1 shared Jacobian->Accuracy owner + characterization
        ↓ V1
      /     \
M2 Issue45  M4 Issue46
migration    migration
  ↓ V2        ↓ V3
      \       /
       V4 integration + post-migration inventory
               ↓
       thin-bridge checkpoint
               ↓
       zero-caller proof
               ↓
      retirement/deletion cuts
```

M2 and M4 are siblings. Both depend on M1, but neither depends on the other.
Therefore an Issue45 migration failure does not invalidate an independently
passing Issue46 migration once V1 is PASS, and vice versa.

## Queue

### V0 — branch-local Stats mapping inventory

- modification: `M0`
- commit: `639bc132a31be430b749ff549ca0498cd576e018`
- scope: add read-only AST inventory harness only
- claim: branch-local caller/import/bridge dependency graph and pre-refactor bridge LOC baseline are observable without text-grep ambiguity
- observed evidence:
  - `ISSUE52_STATS_INVENTORY: PASS`
  - `ISSUE52_STATS_BRIDGE_HELPER_LOC_BASELINE: 93`
  - bridge helpers: Issue45 `44`, Issue46 `42`, PF1 `7`
  - parse failures: `[]`
  - direct `build_accuracy_stats` producer callers: Issue45 + Issue46
- rollback boundary: remove M0 only if the checker itself is invalid
- status: `PASS`

### V1 — shared Jacobian Accuracy owner

- modification: `M1`
- commit: `b68f6fc691ab017f8ebfc8ed55c2ec1eccfdc570`
- path: `qpx_harness/analysis/metrics/accuracy.py`
- scope: extend the existing Accuracy semantic sub-owner with `build_jacobian_accuracy_stats`; concrete Stats construction still routes through `analysis/stats_builder.py`
- claim: shared assembled-vs-FD Jacobian tests map identically to `AccuracyStats`; optional producer-specific matrix comparisons remain additive and distinct; empty Jacobian facts do not invent AccuracyStats
- command:

```bash
python3 -m qpx_harness.analysis.metrics.accuracy
```

- required marker: `QPX_JACOBIAN_ACCURACY_MAPPING_SELFTEST: PASS`
- descendants if FAIL: discard M2 and M4 and any bridge-retirement descendants
- status: `PENDING`

### V2 — Issue45 caller migration

- modification: `M2`
- commit: `10f3cfe2260594e359866d4f6cf5d529d941ec28`
- path: `qpx_harness/issue45_first_linear.py`
- dependency: V1 PASS
- semantic diff: replace producer-local `jacobian["tests"] -> build_accuracy_stats(...)` glue with `build_jacobian_accuracy_stats(...)`; detailed Convergence selection is unchanged
- claim: Issue45 Jacobian Accuracy facts remain identical and KSP/termination/true-residual/variable-residual/scaling-factor selection remains producer-owned
- command:

```bash
python3 -m qpx_harness.issue45_first_linear --self-test
```

- required markers:
  - `ISSUE45_FIRST_LINEAR_STATS_MAPPING_SELFTEST: PASS`
  - `ISSUE45_FIRST_LINEAR_SELFTEST: PASS`
- descendants if FAIL: Issue45-only descendants; do not discard independent Issue46 migration if V1 is PASS
- status: `PENDING`

### V3 — Issue46 caller migration

- modification: `M4`
- commit: `a8a8367ef87ce3b9c4b816903553f96b6b712a8d`
- path: `qpx_harness/issue46_jacobian_localization.py`
- dependency: V1 PASS
- semantic diff: replace producer-local `jacobian["tests"] -> build_accuracy_stats(...)` glue with `build_jacobian_accuracy_stats(...)`; thresholded difference extraction, localization mapping, matrix blocks/counts/L2 remain Issue46-owned
- claim: Issue46 Jacobian Accuracy facts remain identical and thresholded localization/matrix facts remain producer-owned
- command:

```bash
python3 -m qpx_harness.issue46_jacobian_localization --self-test
```

- required markers:
  - `ISSUE46_JAC_LOCALIZATION_STATS_MAPPING_SELFTEST: PASS`
  - `ISSUE46_JAC_LOCALIZATION_SELFTEST: PASS`
  - `ISSUE46_JAC_LOCALIZATION_RUNTIME_SELFTEST: PASS`
- descendants if FAIL: Issue46-only descendants; do not discard independent Issue45 migration if V1 is PASS
- status: `PENDING`

### V4 — integration and post-migration inventory

- modification: validation-only integration gate after V1-V3
- dependencies: V1 PASS; interpret Issue45/Issue46 portions only when their corresponding sibling validation is PASS
- claims:
  - canonical Stats builder remains green;
  - full QPX harness remains green;
  - branch-local AST inventory still parses all source;
  - direct producer calls to `build_accuracy_stats` have been removed from Issue45 and Issue46;
  - bridge-helper LOC can be compared against the pre-refactor baseline `93` before any deletion decision
- commands:

```bash
python3 -m qpx_harness.analysis.stats_builder
python3 scripts/qpx.py self-test
python3 tests/Issue52_stats_mapping_consolidation/inventory.py
```

- required markers:
  - `QPX_STATS_BUILDER_SELFTEST: PASS`
  - `QPX_HARNESS_SELFTEST: PASS`
  - `ISSUE52_STATS_INVENTORY: PASS`
- status: `PENDING`

## Retirement boundary

No bridge/helper deletion is authorized before V1-V4 are PASS and the
thin-bridge checkpoint proves zero semantic ownership. Every deletion then
requires AST/static zero-caller proof and immediate applicable validation.

Issue45 currently retains detailed Convergence fact selection. Issue46 currently
retains thresholded/localized matrix-comparison construction. Therefore neither
bridge is assumed deletion-safe merely because shared Jacobian selection moved.

## Local-round policy

V0 was required because connector search could not prove branch-specific AST
callers on the active non-default branch. M1/M2/M4 were then stacked without
intermediate local rounds because all three are reversible and causally isolated.

V1-V4 should now be discharged in one shell batch using `set -e`. If V1 fails,
M2 and M4 become untrusted descendants. If V2 fails after V1 PASS, only the
Issue45 branch is invalidated. If V3 fails after V1 PASS, only the Issue46 branch
is invalidated. Do not proceed to retirement/deletion until this batch is green.
