# ADFParser JIT environment evidence

**Parent incident:** `INC-ADF-JIT-001` (`docs/incidents/adfparser_jitcompile_failure.md`)  
**Associated work:** Issue #8 `Charged heavy-species mixture diffusion + Poisson coupling`  
**Status:** ACTIVE EVIDENCE  

## Branch-aware diagnostic result

Observed result:

```text
PRIMARY BRANCH: K0_FAIL
K0_exact_step1_control           FAIL rc=1
F1_exact_step1_normal_run        FAIL rc=1
F2_ADParsed_constant_only        FAIL rc=1
F3_ADParsed_from_ADGeneric       FAIL rc=1
F4_ADParsed_from_FV_variable     FAIL rc=1
F5_nonAD_Parsed_same_expression  PASS
ENV_cpp_compile_execute          FAIL rc=127

DECISION
GLOBAL_AD_JIT_ENVIRONMENT_FAILURE
```

## What this result establishes

1. The historical Step-1 input now fails both `--check-input` and a normal run, so the current failure is not specific to `--check-input`.
2. A constant-only `ADParsedFunctorMaterial` fails, so the failure no longer depends on the O/O2 expression, chained functors, FV-variable binding, EOS coupling, or WCNSFV.
3. The equivalent non-AD `ParsedFunctorMaterial` passes, isolating the failure to the AD/JIT path.
4. The generic C++ compiler smoke test returned `127`, meaning the diagnostic runner found no usable generic C++ compiler command in the current runtime PATH.
5. This is still an environment/build-runtime incident, not a heavy-species physics failure.

## Important libMesh build fact

libMesh builds FParser JIT support with a compile-time definition equivalent to:

```make
-DFPARSER_JIT_COMPILER="$(CXX) $(CXXFLAGS)"
```

Therefore FParser JIT may execute the compiler command that was present when libMesh was built, not simply whatever generic `c++` command happens to be available later. The next diagnostic must identify the exact compiler/wrapper command embedded in or invoked by the linked libMesh build.

## Refined hypothesis set

### E1 — build-time JIT compiler/wrapper is missing at runtime

High prior. Examples include a compiler wrapper or environment-provided compiler that existed during the MOOSE/libMesh build but is not currently available in PATH or at its recorded location.

### E2 — compiler exists but FParser's baked command/flags are no longer executable

Examples: wrapper moved, environment/module/conda activation missing, compiler dependency missing, or incompatible runtime flags.

### E3 — TMPDIR/filesystem prevents generated JIT code from executing or being loaded

Lower prior than E1 given the compiler smoke `127`, but still test explicitly.

### E4 — FParser JIT integration is broken even though compiler and TMPDIR are healthy

Consider only if compiler compile/run/shared-library/dlopen smoke tests all pass while constant-only ADParsed still fails.

## Next discriminating batch

The next bundle must collect, in one run:

- QPX binary realpath/version/SHA;
- `PATH`, `CXX`, `TMPDIR`;
- linked libMesh path from `ldd`;
- compiler-related strings from linked libMesh/QPX;
- `libmesh-config` output when available;
- `strace -f -e execve` of the constant-only ADParsed reproducer when available, looking especially for compiler `ENOENT`;
- TMPDIR executable test;
- shared-object copy + `dlopen` test from TMPDIR;
- if any compiler is available, compile/run an executable and compile/`dlopen` a shared object.

## Decision priority

1. compiler `execve(...)=ENOENT` -> `JIT_BUILD_COMPILER_MISSING`;
2. no compiler visible in runtime environment -> `JIT_COMPILER_UNAVAILABLE_IN_RUNTIME_ENV` until exact baked command is identified;
3. TMPDIR execute/load failure -> filesystem/TMPDIR branch;
4. compiler and TMPDIR healthy while F2 still fails -> FParser JIT command/flags/integration branch.
