# Issue53 staged validation queue

**Work ID:** `qpx-stats-builder-decomposition`  
**Issue:** #53  
**Protocol:** `docs/protocols/coding.md` / CODE-13  
**Status:** ACTIVE / V0+V0.5+V1+V2 PASS / D1 NET REPAIRED / D1 LOCAL GATE READY

## Dependency graph

```text
M0 decomposition inventory
        ↓ V0 PASS
M0.5 shared coercion helper
        ↓ V0.5 PASS
      /            \
M1 Efficiency      M2 Convergence
shadow owner        shadow owner
  ↓ V1 PASS           ↓ V2 PASS
      \              /
       first local gate PASS
                ↓
D1 Efficiency facade re-export + monolith removal
                ↓
post-write drift detected + repaired
                ↓
AST structural guard + D1 local validation  ← CURRENT
                ↓
PASS -> D2 Convergence extraction
FAIL -> repair/rollback D1 only; M0-M2 remain accepted
```

## Accepted first gate

User-local evidence reported:

```text
ISSUE53_DECOMPOSITION_INVENTORY: PASS
ISSUE53_STATS_BUILDER_LOC: 942
ISSUE53_STATS_BUILDER_SELFTEST_LOC: 198
ISSUE53_V0: PASS
QPX_ANALYSIS_COERCE_SELFTEST: PASS
ISSUE53_V05: PASS
QPX_EFFICIENCY_STATS_MAPPING_SELFTEST: PASS
QPX_CONVERGENCE_STATS_MAPPING_SELFTEST: PASS
ISSUE53_V1: PASS
ISSUE53_V2: PASS
ISSUE53_FIRST_LOCAL_GATE: PASS
```

### V0 — decomposition inventory

- modification: `M0`
- commit: `191cb57dc96206dab52534fceb855045a728dc53`
- path: `tests/Issue53_stats_builder_decomposition/inventory.py`
- baseline: `stats_builder.py = 942 LOC`; embedded self-test = `198 LOC`
- status: `PASS`

### V0.5 — shared analysis coercion helper

- modification: `M0.5`
- commit: `4ccc2df7adcba4efe2b5b943fd0183caf407a339`
- path: `qpx_harness/analysis/_coerce.py`
- status: `PASS`

### V1 — Efficiency shadow owner

- modification: `M1`
- commit: `806e4d104a8879a1b3eed16daf63fce85fe5bcf1`
- path: `qpx_harness/analysis/metrics/efficiency.py`
- status: `PASS`

### V2 — Convergence shadow owner

- modification: `M2`
- commit: `9b595621d2c8cccfe868aef23af31aa8530578f0`
- path: `qpx_harness/analysis/metrics/convergence.py`
- status: `PASS`

## D1 — Efficiency destructive extraction

Intended semantic cut:

```text
stats_builder.py local Efficiency helpers/build_efficiency_stats
        ↓ removed
analysis/metrics/efficiency.py
        ↓ canonical owner
stats_builder.py
        ↓ re-exports build_efficiency_stats for compatibility/composition
```

Repository commits:

```text
959487a5348488ae7bb3ccd3196e68d1677048ec
  D1 extraction; also introduced an unintended missing ')' outside D1 scope

64d1ab4c074262662b56b9b42f81e59e7db38388
  minimal repair restoring the missing ')' and final newline
```

Post-write verification contained the defect before user-local D1 validation. Incident evidence:

`docs/incidents/issue53_efficiency_extraction_transcription_drift_2026-09-01.md`

MET-22 EPR decision: `PROMOTE_TO_MACHINE_GATE`.

Structural acceptance guard added:

```text
9b0f41882386e74ea7f469a37e78ad58ed8c5d11
tests/Issue53_stats_builder_decomposition/structural_guard.py
```

The guard parses `stats_builder.py`, requires the declared Efficiency owner transfer, rejects unexpected Convergence/core symbol removal at D1, and requires material LOC reduction.

### VD1 — repaired Efficiency extraction validation

- dependency: V0/V0.5/V1/V2 PASS
- net production commits: `959487a...` + repair `64d1ab4...`
- claim:
  - `stats_builder.py` remains syntactically valid;
  - Efficiency implementation is no longer locally owned by `stats_builder.py`;
  - `stats_builder.build_efficiency_stats` remains available through re-export;
  - Convergence/Accuracy/Common/composition ownership is unchanged;
  - PF1 Stats mapping remains green;
  - full QPX P0 remains green;
  - LOC materially decreases from the 942 baseline.
- status: `PENDING`

Required local batch:

```bash
python3 -m py_compile qpx_harness/analysis/stats_builder.py
python3 tests/Issue53_stats_builder_decomposition/structural_guard.py --stage d1
python3 -m qpx_harness.analysis.metrics.efficiency
python3 - <<'PY'
from qpx_harness.analysis import stats_builder
from qpx_harness.analysis.metrics.efficiency import build_efficiency_stats
assert stats_builder.build_efficiency_stats is build_efficiency_stats
print("ISSUE53_D1_REEXPORT: PASS")
PY
python3 -m qpx_harness.analysis.stats_builder
python3 -m qpx_harness.performance.runner --self-test
python3 scripts/qpx.py self-test
python3 tests/Issue53_stats_builder_decomposition/inventory.py
```

Core required markers:

```text
ISSUE53_STRUCTURAL_GUARD_D1: PASS
ISSUE53_STRUCTURAL_GUARD_LOC: <900
QPX_EFFICIENCY_STATS_MAPPING_SELFTEST: PASS
ISSUE53_D1_REEXPORT: PASS
QPX_STATS_BUILDER_SELFTEST: PASS
PF1_STATS_MAPPING_SELFTEST: PASS
QPX_HARNESS_SELFTEST: PASS
ISSUE53_DECOMPOSITION_INVENTORY: PASS
```

## D2 gate

Do not remove Convergence implementation from `stats_builder.py` until VD1 is PASS.

If VD1 passes:

```text
D2 Convergence facade re-export + monolith removal
   -> structural_guard.py --stage d2
   -> Convergence module self-test
   -> Issue45 + PF1 + full-harness P0
```

## Rollback policy

- V0/V0.5/V1/V2 are accepted and survive a D1 failure.
- VD1 FAIL: repair or rollback only D1 net production change; do not discard the validated shadow owners.
- D2 is blocked until VD1 PASS.
- Every subsequent destructive owner extraction receives an immediate structural/local validation boundary.
