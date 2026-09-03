# Issue 91 — real-QVT R3 heavy + electron transport

This workspace constructs the R3 pre-Poisson integration candidate from the accepted Issue15 heavy transport input and the accepted Issue2 electron drift-diffusion contract.

Frozen integration intent:

```text
qvt.msh
heavy mixture transport + charged-heavy migration/correction
electron drift-diffusion
shared prescribed phi = -E0*x
electron lookup pressure = live p
electron lookup gas_temperature = live T_g
Poisson OFF
```

The electron solver representation is now canonically nondimensionalized to avoid the verified large-state Green-Gauss conditioning/cancellation failure:

```text
n_e solver unknown = n_hat ~ O(1)
n_e_physical = n_e_value * n_hat
n_e_value = physical reference density (1e16 m^-3 in the accepted R3 cases)
```

Electron time, diffusion, and drift kernels operate on `n_hat`. Heavy transport and the physical acceptance postprocessors (`n_e_avg`, `n_e_min`, `n_e_max`, `n_e_inventory`) consume `n_e_physical`. This preserves the dimensional physics/checker contract while keeping the FV solver variable at O(1).

The two bounded discriminator cases are:

- `r3_e0`: combined heavy + electron with `E0=0`;
- `r3_econst`: same construction with accepted representative `E0=0.01 V/m`.

Each case starts from the same accepted heavy input bytes (`heavy_base.i`). `prepare.py` performs only the declared R3 composition and writes `input.i` plus `prepare_evidence.json`.

Local QPX integration and scientific runtime are intentionally not part of GitHub pytest. After preparation, run the user-local `qpx-opt --check-input` gate before full runtime. The owning Issue controls EVR accounting.
