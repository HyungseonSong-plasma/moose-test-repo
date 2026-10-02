# Physics experiment workspace

`experiments/` owns repository-local MOOSE/Physics experiment assets. This includes Issue-scoped `test.json` cases, canonical/diagnostic inputs, checkers, scientific reproduction assets, and historical architecture guards.

This directory may contain work that requires the real `physics-opt` production path in governed CI, user-local execution, or both. It is not the pytest namespace.

## Boundary

```text
experiments/  -> Physics/MOOSE cases and scientific/runtime evidence
studies/      -> exploratory scientific analysis
 tests/       -> physics-opt-free pytest validation only
```

`test.json` remains the canonical discovery unit for the reusable Physics regression harness. New experiment work should use an Issue-centric directory such as `experiments/Issue91_real_qvt_r3/...`.

## Execution classes

- `physics-opt`-free construction/characterization belongs in `tests/` and GitHub Actions.
- `physics-opt --check-input` is Physics integration evidence, not full runtime evidence.
- full Physics runtime is scientific execution and follows the owning Issue plus `CORE-05`; provenance-controlled governed CI may be authoritative.
- user-local runtime is a complementary cross-environment validation layer unless the owning Issue explicitly requires a local/environment-specific claim.

Do not place pytest suites in this directory merely because they validate scientific semantics. If no `physics-opt` execution is needed, the validation belongs under `tests/`.

Historical experiment assets may retain `QPX` / `qpx-opt` in names, comments, logs, or archived instructions when that terminology is part of the original evidence. New experiment instructions and current execution contracts use `Physics` / `physics-opt`.


## Reusable diagnostic inventory

Cross-Issue diagnostic baselines may use stable semantic names instead of Issue numbers when their explicit purpose is repeated troubleshooting across later work.  Such entries must carry a runnable `test.json`, provenance, and bounded scientific scope.

| Inventory ID | Path | Purpose |
| --- | --- | --- |
| `electron-diffusion-experiment` | `experiments/2d-icp-electron-diffusion-experiment/` | **STABLE_REUSABLE_BASELINE.** Minimal real-QVT ICP electron diffusion + zero-potential thermal wall-loss baseline. Canonical backing experiment ID: `2d-icp-electron-diffusion-experiment`. |
| `electron-diffusion-energy-experiment` | `experiments/2d-icp-electron-diffusion-energy-experiment/` | **STABLE_REUSABLE_BASELINE.** Electron particle + solved electron-energy diffusion with energy-dependent transport and configurable matched wall-energy loss. |


The reusable simple-case catalog is owned by `experiments/simple_case_inventory.json`.
It contains only qualified reusable sources; future/planned cases are not catalog
entries. Selection is by stable semantic `simple_case_id` or semantic alias, never by
numeric position. Generated cases delegate execution to the existing `physics test`
path and never inherit scientific qualification from their source template.


### Simple-case CLI

```bash
python3 bin/physics.py simple-case list
python3 bin/physics.py simple-case show electron-diffusion-experiment
python3 bin/physics.py simple-case template electron-diffusion-experiment --output /tmp/input.i
python3 bin/physics.py simple-case create electron-diffusion-experiment experiments/my-new-case
python3 bin/physics.py simple-case create electron-diffusion-experiment experiments/my-new-case --input /path/to/new_input.i
python3 bin/physics.py simple-case check
```

`create` first scaffolds the qualified template and its declared assets. If
`--input` is supplied, only the generated `input.i` is replaced afterward.
The derived directory receives `test.json` and `template_origin.json`, so it
can use the existing regression harness while remaining explicitly unqualified
until independently validated.
