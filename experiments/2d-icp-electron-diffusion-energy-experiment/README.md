# 2d-icp-electron-diffusion-energy-experiment

Reusable real-QVT 2-D ICP baseline for **electron particle diffusion + solved electron-energy diffusion**.

This is the second simple-case layer. It starts from the fixed-energy
`electron-diffusion-experiment`, adds the conservative electron-energy state
`c_epsilon`, derives

```text
mean_en = c_epsilon / c_e
```

and feeds that solved mean energy into `PhysicsElectronClosureMaterial`.

The solved system is

```text
d(c_e)/dt       - div(D_e(mean_en) grad(c_e))             = 0
d(c_epsilon)/dt - div(D_epsilon(mean_en) grad(c_epsilon)) = 0
```

The particle wall loss uses the zero-potential thermal collection law. The
electron-energy wall loss is deliberately transport-matched to the bulk
closure:

```text
D_epsilon / D_e = 5/3
Gamma_epsilon = Gamma_e * (5/2) T_e
(Gamma_epsilon/c_epsilon) / (Gamma_e/c_e) = 5/3
```

This choice is specific to this zero-potential diffusion-only baseline. The
general kinetic grounded-sheath owner
`PhysicsFVElectronGroundedSheathEnergyBC` retains the half-Maxwellian
`Gamma_epsilon = Gamma_e (2 T_e + Delta phi)` law.

Electrostatic drift, Poisson, reactions, Joule heating, volumetric energy
sources, and heavy-species evolution remain disabled.

The earlier bounded qualification at Repository CI #540 established the
solved-energy transport chain. A later controlled wall-flux matrix showed that
matching the normalized wall loss to the same 5/3 bulk transport closure removes
the wall-tip temperature bump while preserving particle and energy balance.

```text
physics-opt --check-input        PASS
4-step real physics-opt runtime  PASS
mean_en final range              5.534551394882 .. 5.767975189409 eV
D_e final local range            20394.709196308 .. 20662.419063281 m^2/s
local lookup max relative error  2.69e-14
particle balance max rel error   3.46e-12
energy balance max rel error     1.92e-12
```

Create a derived case with

```bash
python3 bin/physics.py simple-case create \
  electron-diffusion-energy-experiment \
  experiments/my-derived-electron-energy-case
```

Generated cases do not inherit scientific qualification automatically.
