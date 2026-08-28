# Issue #32 real-QVT performance diagnostics

This directory preserves the deterministic test oracle for the profiling/analyzer path used by issue #32.

## Canonical scripts

- `scripts/r32_profile_qpx_case.py` — one-timestep real-QPX profiler already used for EVR1. It runs P2 `--check-input`, streams P3, records MOOSE PerfGraph and PETSc CSV, and does not change dt, solver tolerances, or physics parameters.
- `scripts/r32_build_full_profile_bundle.py` — builds a self-contained local bundle from the accepted `qvt_six_species_transient_inventory` case after verifying the canonical mesh and transport-data SHA256 values.
- `scripts/r32_analyze_profile.py` — classifies a completed profiling result from `summary.json`, `petsc_log.csv`, and optionally `p3_run.log`.

The full QVT mesh and transport database are not duplicated in this repository. The builder locates the accepted local case and verifies byte identity before packaging.

## Runtime preflight

The accepted QPX environment currently requires:

```bash
conda activate moose
```

The generated bundle `run.sh` refuses to execute unless `CONDA_DEFAULT_ENV=moose`.

If P2 reports:

```text
ADFParser::JITCompile() failed. Evaluation not possible.
```

treat it as `ENVIRONMENT_OR_BUILD_FAIL`; no physics/performance conclusion is permitted. This recurrence was resolved by activating the accepted `moose` conda environment.

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
- MOOSE PerfGraph Jacobian self time = 15.722 s across four Jacobian evaluations, including automatic scaling

Reference classification:

```text
JACOBIAN_EVALUATION_DOMINANT
secondary: DIRECT_FACTORIZATION_SIGNIFICANT
secondary: RESIDUAL_EVALUATION_SIGNIFICANT
```

This does **not** yet prove `QPXThermalDiffusionMaterial` is the causal hotspot. EVR2 must localize its `evaluate()`/functor fan-out, AD propagation, pair-collision work, and local dense transport solves before changing representation.

## Build a full local profiling bundle

From repository root:

```bash
conda activate moose
python3 scripts/r32_build_full_profile_bundle.py \
  --qpx-root /path/to/qpx \
  --output r32_full_profile_case.zip
```

Then unzip and run:

```bash
./r32_full_profile_case/run.sh /path/to/qpx-opt T2-heavy
```

## Analyze a profile

```bash
python3 scripts/r32_analyze_profile.py \
  --summary /path/to/summary.json \
  --petsc-log /path/to/petsc_log.csv \
  --perf-log /path/to/p3_run.log
```

## Self-test

From repository root:

```bash
python3 tests/r32_performance/test_r32_analyze_profile.py
```

Expected:

```text
R32_ANALYZER_SELFTEST PASS
```
