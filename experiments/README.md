# Physics experiment workspace

`experiments/` owns repository-local MOOSE/Physics experiment assets. This includes Issue-scoped `test.json` cases, canonical/diagnostic inputs, checkers, scientific reproduction assets, and historical architecture guards.

This directory may contain work that requires the user-local `physics-opt`. It is not the pytest namespace.

## Boundary

```text
experiments/  -> Physics/MOOSE cases and scientific/runtime evidence
studies/      -> exploratory scientific analysis
 tests/       -> physics-opt-free pytest validation only
```

`test.json` remains the canonical discovery unit for the reusable Physics regression harness. New experiment work should use an Issue-centric directory such as `experiments/Issue91_real_qvt_r3/...`.

## Execution classes

- `physics-opt`-free construction/characterization belongs in `tests/` and GitHub Actions.
- `physics-opt --check-input` is local Physics integration and consumes no scientific EVR.
- full Physics runtime is local scientific execution and follows the owning Issue/EVR contract.

Do not place pytest suites in this directory merely because they validate scientific semantics. If no `physics-opt` execution is needed, the validation belongs under `tests/`.

Historical experiment assets may retain `QPX` / `qpx-opt` in names, comments, logs, or archived instructions when that terminology is part of the original evidence. New experiment instructions and current execution contracts use `Physics` / `physics-opt`.