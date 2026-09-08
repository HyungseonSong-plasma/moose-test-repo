# Issue53 decomposition inventory stage-blind false FAIL — 2026-09-01

**Status:** repaired / recorded  
**Affected work:** #53 `qpx-stats-builder-decomposition`  
**Affected validator:** `tests/Issue53_stats_builder_decomposition/inventory.py`

## Incident

After D1 successfully extracted the Efficiency implementation from `stats_builder.py`, the decomposition inventory still enforced baseline-only invariants:

```text
stats_builder_loc >= 700
build_efficiency_stats must remain a local function
build_convergence_stats must remain a local function
build_accuracy_stats must remain a local function
```

Those assumptions were valid only before destructive extraction. At the D1 state, `build_efficiency_stats` is intentionally re-exported from `analysis/metrics/efficiency.py`, so the inventory returned a false FAIL even though the D1 structural guard, Efficiency self-test, facade re-export check, stats-builder self-test, PF1 checks, and full QPX P0 were green.

Because the user ran the batch under interactive `set -e`, the non-zero inventory exit terminated the shell session, making the defect directly user-visible.

## Detection

The failure was inferred from the reported execution sequence:

- all D1 production and integration markers passed;
- execution stopped only at the final inventory command;
- the inventory source still required `build_efficiency_stats` to be a local function and treated later-stage LOC reduction as invalid.

## Root cause

**Stage-blind validation invariant.**

A characterization harness created for the baseline was reused after an intentional ownership transition without making its acceptance logic aware of decomposition stage or facade re-exports.

## Impact

- no production source defect was indicated by the evidence;
- D1 core validation remained green;
- the analyzer produced a false negative;
- the user's interactive terminal exited because `set -e` propagated the false negative;
- D2 work was correctly held until the analyzer defect was repaired.

## Repair

Commit:

```text
a678a275c61fddad5ca7e7d05e259919cee4c5c4
  fix(issue53): make decomposition inventory stage-aware
```

The inventory now:

- records local functions and facade imports separately;
- evaluates stable public facade symbols as `local function OR imported re-export`;
- auto-detects the current decomposition stage;
- removes the obsolete `stats_builder_loc >= 700` baseline-only assertion;
- keeps owner-existence and repository parse checks.

## Learning classification

Primary MET-20 status: `GATE_DEFECT`.

The intended validation gate executed but rejected a valid post-D1 state because its semantic acceptance invariant still represented the baseline architecture.

Applicable pack: `VALIDATE`  
Gate invoked: `yes`  
Detection stage: `user-local validation`  
EPR required: `no` — first classified recurrence of this specific stage-blind decomposition-validator defect and low repair scope.

Primary remediation decision: `REPAIR_GATE_AND_SELFTEST`.

## Prevention direction

For staged structural refactors, validation must distinguish:

```text
stable public facade contract
vs.
current local implementation ownership
```

A symbol intentionally moved behind a compatible re-export is not a missing symbol. Stage-sensitive guards should validate the expected owner transition rather than freeze the baseline implementation topology.
