# Issue #192 — S5-R representative runtime

This directory is the P3 execution surface for the frozen Stage-5 S5-R representative production chemistry case.

The runner does **not** change production physics. It stages the canonical `issue192_s5r` assembly, runs the accepted representative model with the supplied real `physics-opt`, and writes evidence for review. Under `CORE-05`, provenance-controlled governed CI and user-local execution are both eligible runtime-evidence environments.

The primary acceptance path for this work item is governed exact-head CI. User-local execution remains a later integrated cross-environment validation layer rather than a prerequisite for the S5-R CI runtime claim.

It executes two cases with the same final time:

- `baseline`: `dt = 1.0e-4 s`
- `half_dt`: `dt = 5.0e-5 s`

The comparison is intentionally reported as `MEASURED_UNTHRESHOLDED` on the first representative measurement. No new scientific convergence threshold is invented by the harness.

## Run

From the repository root:

```bash
python3 experiments/Issue192_s5r_representative/run.py \
  --physics /absolute/path/to/physics-opt \
  --results-root /absolute/path/to/results
```

`--physics` may be omitted when `PHYSICS_EXECUTABLE` points to the intended executable or `physics-opt` is on `PATH`.

The governed CI workflow builds `physics-opt` from the exact repository head inside the pinned build-base image, verifies dependency identities, invokes this same runner, and archives the resulting evidence bundle. A later user-local integrated validation should reuse the same runner rather than define a second S5-R physics path.

The runner performs `--check-input` for both staged cases before spending the representative runtime budget. It then records:

- canonical 14-channel progress activity;
- heavy-species positivity and constrained-O2 closure;
- chemistry-aware heavy-species and total-mass discrete balances;
- electron-particle discrete balance;
- electron-energy discrete balance using the actual assembled energy owners;
- source-level heavy-mass, oxygen-nuclei, and charge closure;
- solved-Poisson Gauss-law evidence;
- global charge conservation including charged-heavy boundary current;
- nonlinear runtime facts and failure signatures;
- baseline versus half-timestep endpoint sensitivity.

A green run prints:

```text
S5R_REPRESENTATIVE_STATUS: S5R_REPRESENTATIVE_EVIDENCE_READY
```

That status means the representative evidence bundle is ready for scientific review. It does **not** automatically establish Stage-5 acceptance or Integrated Physics Accuracy.

## Harness self-test

The non-runtime self-test does not execute representative physics:

```bash
python3 experiments/Issue192_s5r_representative/run.py --self-test
```

It validates the staged runtime surface and negative controls for state, species, electron-particle, and electron-energy accounting.
