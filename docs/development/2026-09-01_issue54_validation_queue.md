# Issue54 — Electron Inventory Decomposition Validation Queue

## State

`CLOSE-LEVEL DECOMPOSITION APPLIED / SINGLE FINAL LOCAL VALIDATION READY / ISSUE NOT YET CLOSED`

Work ID: `qpx-issue45-electron-inventory-decomposition`

Parent scientific issue: #45.

## Assumed accepted baseline

Per current execution plan, V54-M0, V54-M1, and the pre-cut P0 baseline are treated as PASS for purposes of completing all rollback-local refactor work units before one consolidated local validation.

This does not authorize new scientific evidence. #45 remains scientifically frozen.

## Scientific freeze

The refactor must not consume or authorize #45 EVR3. Frozen contracts remain:

- #45 EVR accounting: 2/3 consumed, EVR3 preserved/not authorized;
- constrained steady physical closure;
- C0/C1 targets and acceptance tolerances;
- boundary conditions and electron-number-balance assumptions;
- solver/KSP/PC/scaling/timestep configuration;
- #46 accepted Jacobian interpretation;
- persisted evidence/summary/marker contracts;
- P0/P1/P2/P3 phase semantics.

No new scientific discriminator is part of Issue54 validation.

## Applied work units

The former monolith `qpx_harness/electron_inventory_nullspace.py` has been decomposed into focused Issue45 owners:

```text
qpx_harness/issue45/
  constants.py
  errors.py
  inventory_structure.py
  closure_schema.py
  closure_model.py
  closure_runtime.py
  orchestration.py
  characterization.py
```

`qpx_harness/electron_inventory_nullspace.py` now acts as the stable compatibility/composition facade and retains CLI routing plus the historical imports required by downstream callers.

The extraction units were applied in semantic order:

```text
Structure
-> Schema
-> Closure Model
-> Runtime Evaluation
-> Orchestration
-> Characterization
-> Thin Facade
```

`qpx_harness/issue45_first_linear.py` and `scripts/qpx.py` were intentionally left unchanged.

## Canonical structural result before local validation

The close-level decomposition commit removes 1873 lines from the historical monolith and redistributes ownership into focused modules. The exact final facade LOC is reported by the final guard rather than used as a precondition.

A final machine gate is available at:

```text
tests/Issue54_electron_inventory_decomposition/final_guard.py
```

It checks:

- thin-facade local implementation state;
- focused owner presence and ownership functions;
- `issue45_first_linear.py` consumer surface;
- facade re-export identity;
- canonical CLI routing;
- import/circular-dependency integrity;
- zero EVR consumption by this refactor.

## Single final local validation

Use a fresh disposable GitHub ZIP snapshot and run diagnostics only:

```text
python3 -m py_compile qpx_harness/electron_inventory_nullspace.py
python3 -m py_compile qpx_harness/issue45/constants.py
python3 -m py_compile qpx_harness/issue45/errors.py
python3 -m py_compile qpx_harness/issue45/inventory_structure.py
python3 -m py_compile qpx_harness/issue45/closure_schema.py
python3 -m py_compile qpx_harness/issue45/closure_model.py
python3 -m py_compile qpx_harness/issue45/closure_runtime.py
python3 -m py_compile qpx_harness/issue45/orchestration.py
python3 -m py_compile qpx_harness/issue45/characterization.py
python3 tests/Issue54_electron_inventory_decomposition/final_guard.py
python3 -m qpx_harness.electron_inventory_nullspace --self-test
python3 -m qpx_harness.issue45_first_linear --self-test
python3 scripts/qpx.py self-test
```

Do **not** run `--closure-run` as Issue54 validation.

## Required final acceptance markers

```text
ISSUE54_FINAL_THIN_FACADE: PASS
ISSUE54_FINAL_FIRST_LINEAR_REEXPORTS: PASS
ISSUE54_FINAL_FIRST_LINEAR_CONSUMERS: PASS
ISSUE54_FINAL_IMPORT_IDENTITY: PASS
ISSUE54_FINAL_CLI_SURFACE: PASS
ISSUE54_FINAL_EVRS_CONSUMED_BY_REFACTOR: 0
ISSUE54_FINAL_GUARD: PASS
ISSUE45_INVENTORY_NULLSPACE_SELFTEST: PASS
ISSUE45_INVENTORY_CLOSURE_RUNTIME_SELFTEST: PASS
ISSUE45_FIRST_LINEAR_SELFTEST: PASS
QPX_HARNESS_SELFTEST: PASS
```

## Local execution contract

Local workspace is a disposable GitHub ZIP snapshot. Local commands are diagnostics only.

Do not require or instruct:

```text
git
cp
rm
mv
source mutation
```

## Closure rule

Issue54 may be closed PASS only after the single final local validation is green. Until then:

```text
production decomposition: APPLIED
scientific state: FROZEN
new #45 EVR consumed: 0
Issue54: OPEN / FINAL VALIDATION PENDING
```
