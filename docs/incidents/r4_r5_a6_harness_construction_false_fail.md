# R4/R5 A6 harness construction false fail

**Status:** OPEN  
**Issue:** #13 `oxygen-heavy-transport-db`  
**Class:** harness/construction  

## Symptom

User-local R4/R5 v2 validation passed P0, the oracle constant-convention self-test, A0-A5, and A7, but all A6 cases failed at P2 `qpx-opt --check-input` before runtime physics evidence was produced.

Two independent harness defects were present.

### H1 -> T1: unsupported output-format parameters

The v2 case generator added

```text
[Outputs]
  csv = true
  precision = 17
  scientific_notation = true
[]
```

The user's MOOSE/QPX build rejects `Outputs/precision` and `Outputs/scientific_notation` as unused parameters.

**Decision:** H1 SUPPORTED.

**Fix candidate:** remove those unsupported top-level output parameters. Do not use `--allow-unused`; the harness should itself be valid.

### H2 -> T2: wrong electron-state requirement in ion-neutral cases

The v2 generator changed the electron-state condition from

```text
any active species charged
```

to

```text
both selected species charged
```

This is incompatible with `QPXThermalDiffusionMaterial` construction semantics. The material validates all active `i <= j` pairs. Therefore a two-species case such as `Op + O2` includes the charged self-pair `Op|Op`, and `Om + O2` includes `Om|Om`. Those dynamic Debye-Huckel self-pairs require `electron_temperature` and `electron_number_density` even though the selected cross pair is ion-neutral.

User-local failures were:

```text
explicit_ionneutral: electron_temperature is required when the active species set contains a charged-charged transport pair
langevin_negative:  electron_temperature is required when the active species set contains a charged-charged transport pair
```

**Decision:** H2 SUPPORTED.

**Fix candidate:** restore electron-state inputs whenever either active species is charged, matching the production constructor's self-pair validation.

## Regression gate

The corrected harness adds a pre-runtime self-test requiring:

```text
neutral_has_no_Te_ne: PASS
ionneutral_has_Te_ne: PASS
negative_ion_has_Te_ne: PASS
unsupported_output_precision_removed: PASS
R4_R5_HARNESS_SELFTEST: PASS
```

Offline regression passes, along with the existing oracle constant-convention self-test and A0-A5/A7 static gates.

## Closure requirement

Keep this incident OPEN until user-local QPX v3 evidence shows P2 construction PASS for all seven A6 cases and allows the A6 numeric production-path parity test to run.
