# Issue #32 real-QVT performance diagnostics

This directory preserves the deterministic EVR1 oracle for Issue #32 while executable logic is owned by the reusable `qpx_harness` package and exposed through the unified `scripts/qpx.py` CLI.

## Ownership

Generic implementation:

```text
qpx_harness/profiling.py   # P2/P3 profiling + evidence capture
qpx_harness/analysis.py    # PETSc/PerfGraph classification
qpx_harness/bundle.py      # declarative local bundle construction
```

Issue-specific case identity, hashes, signatures, accepted paths, environment, and profile defaults are declared in:

```text
tests/r32_performance/profile_spec.json
```

No Issue-32-specific Python executor is required after R3 closure.

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

```bash
conda activate moose
python3 scripts/qpx.py bundle \
  --spec tests/r32_performance/profile_spec.json \
  --qpx-root /path/to/qpx \
  --output r32_full_profile_case.zip
```

## Capture a profile directly

```bash
python3 scripts/qpx.py profile \
  --qpx /path/to/qpx-opt \
  --case-dir /path/to/case \
  --input input.i \
  --label T2-heavy \
  --issue 32 \
  --prefix r32 \
  --output-namespace r32_profiles \
  --num-steps 1
```

## Analyze a profile

```bash
python3 scripts/qpx.py analyze \
  --summary /path/to/summary.json \
  --petsc-log /path/to/petsc_log.csv \
  --perf-log /path/to/p3_run.log \
  --metric-prefix r32
```

## Self-test

The oracle now imports `qpx_harness.analysis` directly:

```bash
python3 tests/r32_performance/test_r32_analyze_profile.py
```

Expected:

```text
R32_ANALYZER_SELFTEST PASS
```
