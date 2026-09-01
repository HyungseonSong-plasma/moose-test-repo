# Issue53 staged validation queue

**Work ID:** `qpx-stats-builder-decomposition`  
**Issue:** #53  
**Protocol:** `docs/protocols/coding.md` / CODE-13  
**Status:** ACTIVE / M0+M0.5+M1+M2 STAGED / FIRST LOCAL GATE READY

## Dependency graph

```text
M0 decomposition inventory
        ↓ V0
M0.5 shared coercion helper
        ↓ V0.5
      /       \
M1 Efficiency M2 Convergence
shadow owner   shadow owner
  ↓ V1           ↓ V2
      \           /
       first local gate
              ↓
PASS -> destructive extraction/migration cuts
FAIL -> keep stats_builder untouched; repair only failed shadow branch
```

M1 and M2 are siblings after M0.5. Neither changes the active `stats_builder.py`
execution path yet, so failure in one does not invalidate the other after V0.5 PASS.

## Queue

### V0 — decomposition inventory

- modification: `M0`
- commit: `191cb57dc96206dab52534fceb855045a728dc53`
- path: `tests/Issue53_stats_builder_decomposition/inventory.py`
- claim: exact branch-local `stats_builder.py` LOC/function ownership and external import/call surfaces are observable before decomposition
- command:

```bash
python3 tests/Issue53_stats_builder_decomposition/inventory.py
```

- required marker: `ISSUE53_DECOMPOSITION_INVENTORY: PASS`
- status: `PENDING`

### V0.5 — shared analysis coercion helper

- modification: `M0.5`
- commit: `4ccc2df7adcba4efe2b5b943fd0183caf407a339`
- path: `qpx_harness/analysis/_coerce.py`
- claim: existing Mapping/float/int/string coercion semantics are available to focused owners without owner-to-facade reverse dependencies
- command:

```bash
python3 -m qpx_harness.analysis._coerce
```

- required marker: `QPX_ANALYSIS_COERCE_SELFTEST: PASS`
- descendants if FAIL: M1 and M2 shadow owners are untrusted
- status: `PENDING`

### V1 — Efficiency shadow owner

- modification: `M1`
- commit: `806e4d104a8879a1b3eed16daf63fce85fe5bcf1`
- path: `qpx_harness/analysis/metrics/efficiency.py`
- dependency: V0.5 PASS
- claim: work counters, PerfGraph/PETSc timings, peak RSS, and memory rows map identically to the current monolith implementation
- command:

```bash
python3 -m qpx_harness.analysis.metrics.efficiency
```

- required marker: `QPX_EFFICIENCY_STATS_MAPPING_SELFTEST: PASS`
- rollback boundary: M1 only; active stats_builder path is unchanged
- status: `PENDING`

### V2 — Convergence shadow owner

- modification: `M2`
- commit: `9b595621d2c8cccfe868aef23af31aa8530578f0`
- path: `qpx_harness/analysis/metrics/convergence.py`
- dependency: V0.5 PASS
- claim: solver config, terminations, residuals, scaling factors, work counters, and trajectory mapping remain identical to the current monolith implementation
- command:

```bash
python3 -m qpx_harness.analysis.metrics.convergence
```

- required marker: `QPX_CONVERGENCE_STATS_MAPPING_SELFTEST: PASS`
- rollback boundary: M2 only; active stats_builder path is unchanged
- status: `PENDING`

## First destructive boundary

Do not remove Efficiency or Convergence code from `stats_builder.py` until V0,
V0.5, V1, and V2 are PASS. After this gate, migrate one domain at a time:

```text
D1 Efficiency facade re-export + monolith removal
   -> immediate module/PF1/full-harness validation

D2 Convergence facade re-export + monolith removal
   -> immediate module/Issue45/PF1/full-harness validation
```

These removals are structural and intentionally require validation immediately
after each deletion/migration boundary rather than being stacked indefinitely.

## Rollback policy

- V0 FAIL: repair inventory only; production source remains untouched.
- V0.5 FAIL: M1/M2 are untrusted; repair shared coercion before interpreting them.
- V1 FAIL with V0.5 PASS: repair/drop Efficiency shadow only; Convergence may survive.
- V2 FAIL with V0.5 PASS: repair/drop Convergence shadow only; Efficiency may survive.
- No `stats_builder.py` rollback is needed at this stage because it has not yet been modified.
