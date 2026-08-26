# Incident: ADFParser JIT compile failure

**Incident ID:** `INC-ADF-JIT-001`  
**Status:** OPEN  
**First associated work:** Issue #8 `Charged heavy-species mixture diffusion + Poisson coupling`  
**First phase observed:** Step 2 input/JIT preflight  
**Failure class:** input/material construction; solver and physics residual evaluation not reached

## Symptom

Observed signature:

```text
*** ERROR ***
ADFParser::JITCompile() failed. Evaluation not possible.
```

The first supplied failure report names:

```text
T1_H1_channel_eos_coupling.i
```

The same error class was also reported for the H2 path.

## What this error currently proves

- An AD parsed expression failed during JIT compilation.
- The failure occurs during `--check-input` / object construction, before the nonlinear solve.
- No conclusion about WCNSFV convergence, mixture diffusion, mass-fraction transport, or EOS physics is justified from this signature alone.

## MOOSE source facts

`ADParsedFunctorMaterial` is implemented through `ParsedFunctorMaterialTempl<true>` and `FunctionParserUtils<true>`.

For parsed functor materials:

- `functor_symbols` may be supplied explicitly;
- when omitted, MOOSE uses the entries in `functor_names` as parser symbols;
- the expression is compiled before the functor material is used in the solve.

For AD parsed objects, MOOSE requires JIT compilation to be enabled and successful. A JIT compilation failure is therefore a construction error rather than a nonlinear convergence failure.

## Evidence history

### Observation 1 — Step 1 known-good baseline

The Step-1 mass-constraint test executed the following AD parsed chain successfully:

```text
w_O -> w_O2 = 1-w_O
    -> Mn = 1/(w_O2/M_O2 + w_O/M_O)
    -> rho_eos
```

Therefore the expression `w_O2 = 1-w_O` is known to have worked previously in the QPX runtime used for Step 1.

### Observation 2 — first construction-isolation ladder

Result:

```text
J1_wO2_only                    FAIL rc=1
J2_add_Mn                      FAIL rc=1
J3_add_rho_raw_symbols         FAIL rc=1
J4_add_rho_safe_symbols        FAIL rc=1
J5_add_transport_properties    FAIL rc=1

DECISION
J1_FAIL
```

Interpretation:

- The first ladder does **not** demonstrate that the primitive expression itself is defective.
- Every J2-J5 case inherited the J1 construction, so once J1 failed those downstream failures supplied no additional discrimination.
- There is now a controlled contradiction: the primitive AD parsed expression passed in the Step-1 context but failed in the stripped J1 context.
- The next task is therefore to identify the **context difference** between the exact Step-1 known-good input and J1, not to modify physics expressions or solver settings.

## Current hypothesis set

### K0 — exact Step-1 control no longer passes `--check-input`

If true, the executable/build/runtime environment has changed or the JIT behavior is non-reproducible relative to the earlier Step-1 run.

### K1 — adding `[Problem] solve = false` changes AD parsed construction behavior

Test by adding only this change to the exact Step-1 input.

### K2 — changing the mesh from the Step-1 1D context to 2D triggers the failure

Test by changing only the mesh dimensionality/topology while preserving the rest of the Step-1 object graph.

### K3 — adding the pressure FV variable triggers the failure

Test by adding only the `p` variable to the exact Step-1 input.

### K4 — the heavily stripped J1 object graph is missing context required for successful construction

This hypothesis is considered only if the exact control and K1-K3 variants all pass while the primitive-only case still fails.

## Next discriminating batch

All tests are construction-only and use `--check-input`.

| Test | Change from exact Step-1 H1 | Decision value |
|---|---|---|
| `K0_exact_step1_control` | none | establishes whether the historical known-good is still reproducible |
| `K1_add_solve_false` | add `[Problem] solve=false` only | isolates solve-disabled context |
| `K2_change_to_2D` | change mesh to 2D only | isolates mesh-context effect |
| `K3_add_pressure_variable` | add `p` FV variable only | isolates extra-variable effect |
| `K4_primitive_only` | stripped primitive J1 context | reproduces the minimal failing context |

### Decision rule

- If `K0` fails: stop. Treat executable/runtime identity as the primary branch; do not interpret K1-K4.
- If `K0` passes and exactly one of K1-K3 fails: that change is the leading context cause.
- If K0-K3 pass but K4 fails: the failure comes from context removed by the stripped harness; create a second removal ladder from exact Step 1.
- If all K0-K4 pass: the earlier J1 failure is not reproducible; record binary/runtime identity and return to the full Step-2 input graph.

## Prevention rule while OPEN

For test bundles containing AD parsed objects:

1. execute `--check-input` before any solve;
2. preserve a previously passing control in every diagnostic batch;
3. change one context element at a time relative to that control;
4. record executable realpath, version, and SHA-256 with the batch result;
5. do not classify JIT construction failures as physics or convergence failures;
6. do not change transport coefficients, timestep, or solver tolerances in response to this error.

## Promotion criteria

This incident may be added to `docs/knowledge/TROUBLESHOOTING_INDEX.md` only after:

1. the minimal reproducer is isolated;
2. the root cause is demonstrated;
3. the fix passes construction and runtime regression;
4. the scope and limitations of the fix are documented.
