# QPX experiment workspace

`experiments/` owns repository-local MOOSE/QPX experiment assets. This includes Issue-scoped `test.json` cases, canonical/diagnostic inputs, checkers, scientific reproduction assets, and historical architecture guards.

This directory may contain work that requires the user-local `physics-opt`. It is not the pytest namespace.

## Boundary

```text
experiments/  -> QPX/MOOSE cases and scientific/runtime evidence
studies/      -> exploratory scientific analysis
 tests/       -> qpx-free pytest validation only
```

`test.json` remains the canonical discovery unit for the reusable QPX regression harness. New experiment work should use an Issue-centric directory such as `experiments/Issue91_real_qvt_r3/...`.

## Execution classes

- qpx-free construction/characterization belongs in `tests/` and GitHub Actions.
- `physics-opt --check-input` is local QPX integration and consumes no scientific EVR.
- full QPX runtime is local scientific execution and follows the owning Issue/EVR contract.

Do not place pytest suites in this directory merely because they validate scientific semantics. If no `physics-opt` execution is needed, the validation belongs under `tests/`.
