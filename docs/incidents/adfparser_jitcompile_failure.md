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

The supplied failure report names:

```text
T1_H1_channel_eos_coupling.i
```

The user also reported the same error class in H2. The exact H2 object/file signature is not yet captured, so the two occurrences must not yet be assumed to have the same root cause.

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

## Current hypotheses

### J1 — environment-wide AD JIT support is unavailable

**Prior:** low.

Reason: the Step-1 mass-constraint baseline already executed AD parsed functor materials successfully in the same QPX environment. A global absence of JIT support is therefore unlikely unless the executable/environment changed.

### J2 — a specific expression/symbol set causes JIT failure

**Status:** SURVIVES.

The Step-2 closure introduced new parsed expressions and/or symbol naming on top of the Step-1-proven closure.

### J3 — a chained AD parsed-functor dependency triggers the failure

**Status:** SURVIVES.

Step 2 chains parsed properties such as `w_O -> w_O2 -> Mn -> rho`, and H2 extends that chain further to `x_O2 -> D_O_mix`.

## Next discriminating tests

Use construction-only tests. Do not run flow or species physics until all tests pass `--check-input`.

| Test | Construction | Purpose |
|---|---|---|
| `J1_wO2_only` | only `w_O2 = 1-w_O` | verify the Step-1-proven primitive expression |
| `J2_add_Mn` | `w_O2 -> Mn` | test first parsed-property chain |
| `J3_add_rho_raw_symbols` | add `rho(p,Mn)` using actual functor names | test the new Step-2 EOS parser form |
| `J4_add_rho_safe_symbols` | same rho expression with explicit symbols such as `pres meanM` | test symbol-remapping hypothesis |
| `J5_add_transport_properties` | add `x_O2 -> D_O_mix` only after J4 | isolate H2-only parsed chain |

### Decision rule

- First failing `J#` identifies the smallest construction that reproduces the incident.
- If `J3` fails and `J4` passes, classify root cause as parser-symbol/JIT incompatibility for the raw names.
- If `J2` already fails, investigate chained AD parsed properties before EOS/WCNSFV.
- If all J1-J5 pass, the failure belongs to the full Step-2 object graph rather than these parsed expressions and a new hypothesis set is required.

## Prevention rule while OPEN

For test bundles containing AD parsed objects:

1. execute `--check-input` before any solve;
2. keep parsed expressions in a construction-isolation ladder;
3. use explicit `functor_symbols` for new expressions until the incident is closed;
4. do not classify JIT construction failures as physics or convergence failures;
5. do not change transport coefficients, timestep, or solver tolerances in response to this error.

## Promotion criteria

This incident may be added to `docs/knowledge/TROUBLESHOOTING_INDEX.md` only after:

1. the minimal reproducer is isolated;
2. the root cause is demonstrated;
3. the fix passes construction and runtime regression;
4. the scope and limitations of the fix are documented.
