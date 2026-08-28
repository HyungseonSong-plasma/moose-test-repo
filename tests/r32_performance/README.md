# Issue #32 real-QVT performance diagnostics

This directory preserves the deterministic EVR1 oracle for Issue #32 while the executable logic is owned by the reusable `qpx_harness` package.

## R2 ownership

Generic implementation:

```text
qpx_harness/profiling.py   # P2/P3 profiling + evidence capture
qpx_harness/analysis.py    # PETSc/PerfGraph classification
qpx_harness/bundle.py      # declarative local bundle construction
```

Issue-specific compatibility entry points remain available:

```text
scripts/r32_profile_qpx_case.py
scripts/r32_analyze_profile.py
scripts/r32_build_full_profile_bundle.py
```

These wrappers must not regain duplicated runtime/analyzer/bundle logic.

Issue-specific case identity, hashes, signatures, accepted paths, environment, and profile defaults are declared in:

```text
tests/r32_performance/profile_spec.json
```

The preferred new local workspace is:

```text
<QPX_ROOT>/temp/test_workspace/Issue32_performance_localization/T2_heavy/
```

Historical `regression_workspace/.../qvt_six_species_transient_inventory` paths remain accepted during migration so prior validated case provenance is not invalidated by a path-only move.

## Runtime preflight

The accepted QPX environment requires:

```bash
conda activate moose
```

The generated bundle `run.sh` enforces `CONDA_DEFAULT_ENV=moose`.

If P2 reports `ADFParser::JITCompile() failed. Evaluation not possible.`, classify it as `ENVIRONMENT_OR_BUILD_FAIL`; no physics/performance conclusion is permitted.

## EVR1 reference

`evr1_t2_heavy.json` records the sanitized T2-heavy reference result from 2026-08-28:

- 21,132 DOFs
- one physical timestep, `dt = 1e-4`
- 3 nonlinear iterations
- 3 linear iterations
- 4 residual evaluations
- PETSc `SNESJacobianEval = 12.1323 s`
- `PCSetUp = 7.49414 s`
- `KSPSolve = 0.233045 s`
- MOOSE PerfGraph Jacobian self time = 15.722 s across four Jacobian evaluations

Reference classification:

```text
JACOBIAN_EVALUATION_DOMINANT
secondary: DIRECT_FACTORIZATION_SIGNIFICANT
secondary: RESIDUAL_EVALUATION_SIGNIFICANT
```

This does not prove `QPXThermalDiffusionMaterial` is the causal hotspot. EVR2 must localize `evaluate()`/functor fan-out, AD propagation, pair-collision work, and local dense transport solves before representation changes.

## Build a local profiling bundle

Compatibility command:

```bash
conda activate moose
python3 scripts/r32_build_full_profile_bundle.py \
  --qpx-root /path/to/qpx \
  --output r32_full_profile_case.zip
```

Generic command for future issues:

```bash
python3 -m qpx_harness.bundle \
  --spec /path/to/profile_spec.json \
  --qpx-root /path/to/qpx \
  --output profile_bundle.zip
```

## Analyze a profile

```bash
python3 scripts/r32_analyze_profile.py \
  --summary /path/to/summary.json \
  --petsc-log /path/to/petsc_log.csv \
  --perf-log /path/to/p3_run.log
```

## Self-test

```bash
python3 tests/r32_performance/test_r32_analyze_profile.py
```

Expected:

```text
R32_ANALYZER_SELFTEST PASS
```
