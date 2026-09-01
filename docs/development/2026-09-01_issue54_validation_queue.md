# Issue54 — Electron Inventory Decomposition Validation Queue

## State

`M0/M1 DIAGNOSTICS STAGED / PRODUCTION UNCHANGED / DESTRUCTIVE CUT BLOCKED`

Work ID: `qpx-issue45-electron-inventory-decomposition`

Parent scientific issue: #45.

## Scientific freeze

This refactor must not consume or authorize #45 EVR3. The following remain frozen:

- #45 EVR accounting: 2/3 consumed, EVR3 preserved/not authorized;
- constrained steady physical closure;
- C0/C1 targets and acceptance tolerances;
- boundary conditions and electron-number-balance assumptions;
- solver/KSP/PC/scaling/timestep configuration;
- #46 accepted Jacobian interpretation;
- persisted evidence/summary/marker contracts;
- P0/P1/P2/P3 phase semantics.

No new scientific discriminator is part of Issue54 validation.

## Local execution contract

Local workspace is a disposable GitHub ZIP snapshot.

Local commands are diagnostics only.

Do not require or instruct:

```text
git
cp
rm
mv
source mutation
```

Canonical repository mutation occurs in GitHub only after the preceding diagnostic gate is accepted.

## Queue

### V54-M0 — decomposition inventory

Status: `STAGED / LOCAL EVIDENCE REQUIRED`

Command:

```text
python3 tests/Issue54_electron_inventory_decomposition/inventory.py
```

Acceptance markers:

```text
ISSUE54_M0_FIRST_LINEAR_CONTRACT: PASS
ISSUE54_M0_CLI_CONTRACT: PASS
ISSUE54_M0_REQUIRED_TOP_LEVEL: PASS
ISSUE54_M0_INVENTORY: PASS
```

Evidence obligations:

- exact source LOC;
- exact embedded self-test LOC;
- every top-level function classified;
- per-function LOC and internal call graph;
- semantic constant use by owner category;
- branch-local consumers;
- exact downstream surface used by `issue45_first_linear.py`;
- canonical CLI dependency.

Rollback boundary: diagnostic file only. Production owner is unchanged.

### V54-M1 — compatibility baseline

Status: `STAGED / LOCAL EVIDENCE REQUIRED`

Command:

```text
python3 tests/Issue54_electron_inventory_decomposition/compatibility_guard.py
```

Acceptance markers:

```text
ISSUE54_M1_SCIENTIFIC_CONSTANTS: PASS
ISSUE54_M1_CLI_SURFACE: PASS
ISSUE54_M1_FIRST_LINEAR_SURFACE: PASS
ISSUE54_M1_COMPATIBILITY_GUARD: PASS
```

The guard freezes the current module/CLI/downstream surface without running QPX.

Rollback boundary: diagnostic file only. Production owner is unchanged.

### V54-P0 — existing behavior baseline

Status: `PENDING V54-M0/M1`

After M0/M1 PASS, validate the existing production owner before any extraction:

```text
python3 -m qpx_harness.electron_inventory_nullspace --self-test
python3 -m qpx_harness.issue45_first_linear --self-test
python3 scripts/qpx.py self-test
```

No closure runtime or new EVR is authorized.

### First extraction boundary

Status: `BLOCKED`

No function may be removed from `qpx_harness/electron_inventory_nullspace.py` until V54-M0, V54-M1, and V54-P0 are PASS.

After those gates, use the M0 call graph to select the first rollback-local semantic owner. Current architectural hypothesis is Structure-first, but M0 evidence is authoritative.

The first extraction must follow:

```text
additive owner staging
-> owner-local characterization
-> compatibility identity proof
-> only then destructive removal/re-export from the monolith
```

## Production mutation status

As of this queue creation:

```text
qpx_harness/electron_inventory_nullspace.py: UNCHANGED
qpx_harness/issue45_first_linear.py: UNCHANGED
scripts/qpx.py: UNCHANGED
new scientific runtime: NONE
#45 EVR consumed by Issue54: 0
```
