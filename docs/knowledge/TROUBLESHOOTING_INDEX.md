# Troubleshooting Index

This index maps recurring symptoms to incident records and minimal regression cases.

| Symptom / keyword | First reference | Status |
|---|---|---|
| `DIVERGED_LINE_SEARCH` on repeated transient solve of algebraic FV potential | `docs/incidents/m5_ion_drift_failure_history.md` | residual-floor mechanism CLOSED for pure `phi` case |
| Solved-potential ion drift differs from prescribed-field reference | `docs/incidents/m5_ion_drift_failure_history.md` | investigation in progress |
| Wall migration postprocessor is nonzero but transient inventory does not include the same loss | `tests/m5_plasma_charge/ion_wall_migration_state/` | isolated diagnostic cases |
| EOS identity appears to fail when `rho_avg` is approximated by `(rho_min + rho_max)/2` | `docs/incidents/step2_eos_validation_aggregation_error.md` | CLOSED; use matching spatial-average operators |
| Independent oracle shows the same small multiplicative error for every physics state while state sensitivity still passes | `docs/incidents/r3_thermal_diffusion_gas_constant_scale_mismatch.md` | CLOSED; check host constant/unit convention before modifying production physics |
| Production-parity oracle fails by a transport-class-dependent but reproducible vector while source/provenance gates pass | `docs/incidents/r4_a6_production_oracle_constant_convention_mismatch.md` | CLOSED; separate upstream source constants from production numerical conventions |
| `--check-input` fails before runtime because generated test input omits state required by charged self-pairs or contains unsupported output knobs | `docs/incidents/r4_r5_a6_harness_construction_false_fail.md` | CLOSED; validate full active-set constructor contract |
| `Invalid function ... Syntax error in parameter 'Vars' given to FunctionParser::Parse()` | `docs/incidents/functionparser_reserved_symbol_collision.md` | CLOSED; machine-enforced parser-symbol P0 added |

## Reusable pattern: algebraic variable inside a transient solve

Observed pattern:

```text
Time Step n:
large initial residual -> tiny residual -> relative convergence PASS

Time Step n+1:
already-small initial residual -> numerical residual floor
-> absolute tolerance below floor
-> line-search failure
```

First diagnostic:

```text
compare nl_abs_tol with measured residual floor
```

Do not modify physics coefficients or timestep before checking this condition.

## Reusable pattern: validation aggregation mismatch

When checking an integral or average identity, do not replace a domain average with a midpoint of extrema.

Invalid example:

```text
rho_avg ~= 0.5 * (rho_min + rho_max)
```

Correct approach:

```text
compare avg(rho) against an expression formed with compatible spatial averaging and weighting
```

For the Step-2 O2/O EOS test, `Mn` was spatially uniform, so the correct identity was

```text
avg(rho) = avg(p) * Mn / (R*T)
```

The corrected regression produced `EOS_rel_error = 2.198e-14`.

## Reusable pattern: independent-oracle convention mismatch

If an independent oracle differs from production by nearly the same multiplicative factor across unrelated states, while the intended state sensitivities and branch discriminators remain correct, treat a downstream constant/unit/convention mismatch as a primary hypothesis.

Recommended discriminator:

```text
1. Compare a dimensionless/intermediate observable that does not contain the suspect conversion.
2. Compare the final dimensional observable.
3. Infer the effective scale/constant from production output.
4. Mutation-test the oracle convention before changing production physics.
```

The R3 thermal-diffusion case preserved `kT`, `Te` sensitivity, `ne` sensitivity, and Coulomb-branch sensitivity, while only final `D_T` carried a uniform ~`1.17e-5` offset. The cause was the oracle using modern exact `k_B*N_A` while QPX used its established host EOS `R` convention.

## Reusable pattern: source provenance vs production numerical contract

A source/provenance gate and a production-parity gate answer different questions. Keep source-data checks pinned to the upstream model, but let a production-parity oracle use the production implementation's declared numerical constants while remaining algorithmically independent.

If replacing production constants with historical upstream constants reproduces the external failure vector, classify the defect as an oracle-contract mismatch rather than a production-physics failure.

## Reusable pattern: active-set constructor validation

A targeted pair test may still trigger constructor checks for self-pairs and other pairs in the active species set. Generate inputs from the full constructor contract, not only the cross-pair being observed.

For charged-heavy transport, one charged species is enough to create a charged self-pair during `i <= j` validation, so `Te/ne` may be required even for an ion-neutral target cross-pair. Unsupported input parameters are harness failures; do not mask them with `--allow-unused`.

## Reusable pattern: FunctionParser variable namespace

For `ParsedFunctorMaterial` / `ADParsedFunctorMaterial`, a mathematically valid expression can still fail before evaluation if its parser-symbol namespace is invalid.

MOOSE appends coordinate/time symbols `x,y,z,t` and provides parser constants `pi,e`. Do not reuse those names as custom `functor_symbols`; also reject duplicate aliases and implicit `functor_names` collisions when `functor_symbols` is omitted.

Required first action for

```text
Syntax error in parameter 'Vars' given to FunctionParser::Parse()
```

is:

```text
python3 scripts/validate_parser_symbols.py <input.i>
```

Do not change physics or solver settings before this namespace check.

## Incident promotion rule

An incident can be promoted from `docs/incidents/` to reusable knowledge only after:

1. root cause is isolated,
2. fix is verified,
3. regression gate passes,
4. scope/limitations are documented.
