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

The two bounded discriminator cases are:

- `r3_e0`: combined heavy + electron with `E0=0`;
- `r3_econst`: same construction with accepted representative `E0=0.01 V/m`.

Each case starts from the same accepted heavy input bytes (`heavy_base.i`). `prepare.py` performs only the declared R3 composition and writes `input.i` plus `prepare_evidence.json`.

Local QPX integration and scientific runtime are intentionally not part of GitHub pytest. After preparation, run the user-local `qpx-opt --check-input` gate before full runtime. The owning Issue controls EVR accounting.
