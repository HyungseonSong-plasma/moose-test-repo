# Issue52 staged validation queue

**Work ID:** `qpx-stats-mapping-consolidation-retirement`  
**Issue:** #52  
**Protocol:** `docs/protocols/coding.md` / CODE-13  
**Status:** ACTIVE / M0 INVENTORY HARNESS READY / IMPLEMENTATION CUTS BLOCKED ON INVENTORY EVIDENCE

## Dependency graph

```text
M0 AST inventory/proof harness
        ↓ V0
M1 canonical Jacobian->Accuracy helper + characterization
        ↓ V1
      /     \
M2 Issue45  M4 Issue46
migration    migration
  ↓ V2        ↓ V3
M3 Issue45   M5 Issue46
preservation localization-preservation
      \       /
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
- command:

```bash
python3 tests/Issue52_stats_mapping_consolidation/inventory.py
```

- required marker: `ISSUE52_STATS_INVENTORY: PASS`
- required evidence: JSON block between `ISSUE52_STATS_INVENTORY_JSON_BEGIN/END`
- rollback boundary: remove M0 only if the checker itself is invalid
- status: `PENDING`

### V1 — canonical Jacobian Accuracy helper

- modification: `M1` — not yet executed
- dependency: V0 evidence sufficient to confirm caller graph
- claim: shared assembled-vs-FD Jacobian tests map identically to `AccuracyStats` while producer-specific matrix/localization facts remain separate
- validation: focused builder characterization + existing Stats builder self-test
- descendants if FAIL: discard M2 and M4 and any bridge-retirement descendants
- status: `PENDING / NOT IMPLEMENTED`

### V2 — Issue45 caller migration

- modification: `M2` — not yet executed
- dependency: V1 PASS
- claim: Issue45 Jacobian Accuracy facts remain identical and detailed Convergence fact selection remains producer-owned
- validation marker: `ISSUE45_FIRST_LINEAR_STATS_MAPPING_SELFTEST: PASS`
- descendants if FAIL: Issue45-only descendants; do not discard independent Issue46 migration if V1 is PASS
- status: `PENDING / NOT IMPLEMENTED`

### V3 — Issue46 caller migration

- modification: `M4` — not yet executed
- dependency: V1 PASS
- claim: Issue46 Jacobian Accuracy facts remain identical and thresholded localization/matrix facts remain producer-owned
- validation markers:
  - `ISSUE46_JAC_LOCALIZATION_STATS_MAPPING_SELFTEST: PASS`
  - `ISSUE46_JAC_LOCALIZATION_SELFTEST: PASS`
- descendants if FAIL: Issue46-only descendants; do not discard independent Issue45 migration if V1 is PASS
- status: `PENDING / NOT IMPLEMENTED`

## Retirement boundary

No bridge/helper deletion is authorized before V1-V3 are PASS and the
thin-bridge checkpoint proves zero semantic ownership. Every deletion then
requires AST/static zero-caller proof and immediate applicable validation.

## Local-round policy

V0 is the first required local execution because GitHub connector code search
cannot prove branch-specific AST callers on the active non-default branch.
After V0 evidence is returned, continue M1/M2/M4 without another local round
until the next CODE-13 discharge point unless a destructive/ambiguous boundary
is reached.
