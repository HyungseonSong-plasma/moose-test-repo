# Incident: ADFParser JIT compile failure

**Incident ID:** `INC-ADF-JIT-001`  
**Status:** MONITORING  
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

- An AD parsed expression failed during JIT compilation in the failing runs.
- Those failures occurred during `--check-input` / object construction, before the nonlinear solve.
- No conclusion about WCNSFV convergence, mixture diffusion, mass-fraction transport, or EOS physics is justified from that signature alone.

## MOOSE / libMesh source facts

`ADParsedFunctorMaterial` is implemented through `ParsedFunctorMaterialTempl<true>` and `FunctionParserUtils<true>`.

For parsed functor materials:

- `functor_symbols` may be supplied explicitly;
- when omitted, MOOSE uses the entries in `functor_names` as parser symbols;
- the expression is compiled before the functor material is used in the solve.

For AD parsed objects, MOOSE requires JIT compilation to be enabled and successful.

libMesh FParser JIT also has two environment-relevant implementation details:

1. the JIT compiler command is built from the libMesh build-time `$(CXX) $(CXXFLAGS)` configuration rather than necessarily from the current shell's generic `c++` command;
2. compiled JIT objects are cached in a local `.jitcache` directory and may be loaded with `dlopen` on later runs.

Therefore current-shell compiler discovery is only a supporting diagnostic and must not override the direct ADParsed construction result.

## Evidence history

### Observation 1 — Step 1 known-good baseline

The Step-1 mass-constraint test executed the following AD parsed chain successfully:

```text
w_O -> w_O2 = 1-w_O
    -> Mn = 1/(w_O2/M_O2 + w_O/M_O)
    -> rho_eos
```

Therefore the expression `w_O2 = 1-w_O` is known to have worked previously in QPX.

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
- There was a controlled contradiction: the primitive AD parsed expression passed in the Step-1 context but failed in the stripped J1 context.

### Observation 3 — branch-aware environment probe

A later branch-aware run reported:

```text
K0_exact_step1_control           FAIL
F1_exact_step1_normal_run        FAIL
F2_ADParsed_constant_only        FAIL
F3_ADParsed_from_ADGeneric       FAIL
F4_ADParsed_from_FV_variable     FAIL
F5_nonAD_Parsed_same_expression  PASS
ENV_cpp_compile_execute          FAIL rc=127
```

This narrowed the failing run to the AD FParser/JIT path, but did not establish a permanent environment root cause.

### Observation 4 — direct environment comparison

The dedicated environment probe was then run in two shell states.

With the conda environment deactivated:

```text
F2 constant-only ADParsed        PASS
TMP executable                   PASS
TMP copied-so dlopen             PASS
Compiler compile/shared/dlopen   FAIL rc=127
```

With the `moose` conda environment activated:

```text
F2 constant-only ADParsed        PASS
TMP executable                   PASS
TMP copied-so dlopen             PASS
Compiler compile/shared/dlopen   PASS
```

The probe analyzer labelled the deactivated case `COMPILER_OR_SHARED_BUILD_FAILURE`, but that classification was a harness logic defect: the direct target `F2 constant-only ADParsed` had already passed. The generic compiler smoke test must not override a passing FParser JIT construction test.

This means:

- ADParsed/FParser JIT was healthy in both of these later environment-probe runs;
- activating conda clearly restores generic compiler commands in `PATH`, but it has **not** been demonstrated to be the cause of FParser JIT recovery;
- the test harness analyzer defect is separate from the original runtime incident.

### Observation 5 — cold-cache recovery gate

A fresh cold-cache batch then produced:

```text
F2 cold check           PASS
Step1 cold check        PASS
Step1 cold normal run   PASS

T1 cold check           PASS
T1 cold normal run      PASS
T2 cold check           PASS
T2 cold normal run      PASS
```

This is strong evidence that the AD FParser JIT path is currently healthy without relying on a pre-existing local `.jitcache`.

The incident is therefore no longer blocking Issue #8 physics work. It remains in **MONITORING** rather than CLOSED because the original failure mechanism was not reproducibly isolated.

## Current hypothesis set

### HJ1 — transient/environment-sensitive JIT failure

**Status:** SURVIVES as historical explanation only.

The exact mechanism was not isolated, but the current cold-cache regression is healthy.

### HJ2 — local `.jitcache` state affected reproducibility

**Status:** NOT PROVEN.

Cold-cache recovery passes, so warm-cache dependence is not required for the current healthy state.

### HJ3 — the Step-2 physics/input expressions are the root cause

**Status:** REJECTED for the original JIT incident.

Constant-only ADParsed construction failed in the earlier failing run, while the same Step-2 inputs now pass cold-cache construction and runtime.

## Operating rule while MONITORING

For test bundles containing AD parsed objects:

1. preserve a previously passing control when practical;
2. distinguish cold-cache and warm-cache runs if JIT failure recurs;
3. record executable/environment identity for recurrence analysis;
4. treat `ADParsedFunctorMaterial` construction itself as the primary JIT health signal;
5. use compiler/TMPDIR/dlopen probes as supporting diagnostics only;
6. do not classify JIT construction failures as physics or nonlinear convergence failures;
7. do not change transport coefficients, timestep, or solver tolerances in response to this error.

## Closure / promotion criteria

This incident may be CLOSED and promoted to `docs/knowledge/TROUBLESHOOTING_INDEX.md` only if either:

1. the original root cause is reproducibly isolated and fixed; or
2. a clearly bounded environment/cache-sensitive recurrence pattern is demonstrated.

Until then, the cold-cache recovery result is retained as a regression gate and the incident remains MONITORING.
