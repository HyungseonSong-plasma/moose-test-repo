# R4/R5 A6 harness construction false fail

**Status:** CLOSED  
**Issue:** #13 `oxygen-heavy-transport-db`  
**Class:** harness/construction

## Symptom

The user-local R4/R5 v2 run passed P0, the oracle constant-convention self-test, A0-A5, and A7, but all A6 cases failed at P2 `qpx-opt --check-input` before runtime physics evidence.

Two independent harness defects were present.

## H1 -> T1: unsupported output-format parameters

The v2 generator added top-level `Outputs/precision` and `Outputs/scientific_notation`. The user's MOOSE/QPX build rejects these as unused parameters.

**Decision:** H1 SUPPORTED.

**Fix:** remove the unsupported parameters. Do not use `--allow-unused` to hide an invalid harness.

## H2 -> T2: wrong electron-state condition

The v2 generator supplied `Te/ne` only when both selected species were charged. `QPXThermalDiffusionMaterial` validates all active `i <= j` pairs, so `Op + O2` still includes `Op|Op` and `Om + O2` includes `Om|Om`. Those charged self-pairs require `electron_temperature` and `electron_number_density`.

**Decision:** H2 SUPPORTED.

**Fix:** supply electron state whenever the active species set contains a charged species, matching production constructor semantics.

## Regression gate

The v3 harness added a pre-runtime self-test:

```text
neutral_has_no_Te_ne: PASS
ionneutral_has_Te_ne: PASS
negative_ion_has_Te_ne: PASS
unsupported_output_precision_removed: PASS
R4_R5_HARNESS_SELFTEST: PASS
```

## Closure evidence

The user-local v3 run then showed `check-input rc=0` and `runtime rc=0` for all seven A6 cases. A6 numeric parity also passed for every case with maximum relative error `2.526e-08`, followed by:

```text
A6_QPX_PRODUCTION_PATH: PASS
BATCH_A_PASS
R4_R5_PASS
```

**Closure decision:** the v2 failures were construction-harness defects, not physics failures.

## Reusable lesson

For MOOSE/QPX production-path tests, the generated input must honor constructor-level validation over the full active species set, not only the cross-pair the test intends to observe. Also treat unused input parameters as harness defects rather than bypassing them with permissive command-line flags.
