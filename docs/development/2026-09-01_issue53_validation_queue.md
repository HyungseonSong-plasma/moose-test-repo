# Issue53 staged validation queue

**Work ID:** `qpx-stats-builder-decomposition`  
**Issue:** #53  
**Protocol:** `docs/protocols/coding.md` / CODE-13  
**Status:** ACTIVE / V0+V0.5+V1+V2 PASS / D1 CORE PASS / INVENTORY GATE DEFECT REPAIRED / VALIDATOR RECHECK READY

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
AST structural guard + D1 core validation PASS
                ↓
stage-blind inventory false FAIL detected + repaired
                ↓
fixed inventory recheck  ← CURRENT
                ↓
PASS -> VD1 COMPLETE -> D2 Convergence extraction
FAIL -> repair inventory validator only unless new production evidence appears
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

Post-write verification contained the transcription defect before user-local D1 validation. Incident evidence:

`docs/incidents/issue53_efficiency_extraction_transcription_drift_2026-09-01.md`

MET-22 EPR decision: `PROMOTE_TO_MACHINE_GATE`.

Structural acceptance guard added:

```text
9b0f41882386e74ea7f469a37e78ad58ed8c5d11
tests/Issue53_stats_builder_decomposition/structural_guard.py
```

### VD1 — repaired Efficiency extraction validation

User-local D1 core evidence:

```text
ISSUE53_STRUCTURAL_GUARD_D1: PASS
ISSUE53_STRUCTURAL_GUARD_LOC: 836
QPX_EFFICIENCY_STATS_MAPPING_SELFTEST: PASS
ISSUE53_D1_REEXPORT: PASS
QPX_STATS_BUILDER_SELFTEST: PASS
PF1_STATS_MAPPING_SELFTEST: PASS
QPX_PERFORMANCE_CORE_SELFTEST: PASS
QPX_HARNESS_SELFTEST: PASS
```

This proves the production D1 path and full P0 integration are green at `836 LOC`, a reduction of `106 LOC` from the `942` baseline.

The final inventory command then returned a false FAIL because its baseline-only invariants still required `build_efficiency_stats` to be a local function. Under interactive `set -e`, that non-zero exit terminated the user's shell session.

Validator incident:

`docs/incidents/issue53_inventory_stage_blind_false_fail_2026-09-01.md`

Validator repair commit:

```text
a678a275c61fddad5ca7e7d05e259919cee4c5c4
  fix(issue53): make decomposition inventory stage-aware
```

The repaired inventory now evaluates stable facade symbols as local definitions or re-exported imports and auto-detects decomposition stage.

- D1 production/core status: `PASS`
- final validator status: `RECHECK PENDING`
- D2 status: `BLOCKED UNTIL FIXED INVENTORY PASS`

## Current local recheck

Run without interactive `set -e` so a validator failure prints rather than terminating the shell:

```bash
git pull --ff-only
python3 tests/Issue53_stats_builder_decomposition/inventory.py
RC=$?
echo "ISSUE53_FIXED_INVENTORY_RC: $RC"
```

Required markers for VD1 completion:

```text
ISSUE53_DECOMPOSITION_INVENTORY: PASS
ISSUE53_STATS_BUILDER_LOC: 836
ISSUE53_DECOMPOSITION_STAGE: D1_EFFICIENCY_EXTRACTED
ISSUE53_FIXED_INVENTORY_RC: 0
```

## D2 gate

Do not remove Convergence implementation from `stats_builder.py` until the repaired inventory recheck passes.

After PASS:

```text
D2 Convergence facade re-export + monolith removal
   -> structural_guard.py --stage d2
   -> Convergence module self-test
   -> Issue45 + PF1 + full-harness P0
```

## Rollback policy

- V0/V0.5/V1/V2 remain accepted.
- D1 production/core validation is accepted.
- A repaired-inventory recheck failure is treated as a validator defect unless it exposes new production evidence.
- D2 remains blocked until the fixed inventory passes.
- Every subsequent destructive owner extraction receives an immediate structural/local validation boundary.
