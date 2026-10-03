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

The particle wall loss uses the zero-potential thermal collection law.
`PhysicsFVElectronGroundedSheathEnergyBC` now takes the dimensionless
`energy_per_particle_te_factor` as a functor and evaluates

```text
Gamma_epsilon = Gamma_e * (alpha*T_e + Delta_phi)
```

with `alpha=2.0` as the default kinetic half-Maxwellian closure. This
diffusion-only baseline explicitly supplies `energy_wall_te_factor=2.5`, so

```text
D_epsilon / D_e = 5/3
(Gamma_epsilon/c_epsilon) / (Gamma_e/c_e) = 5/3
```

The coefficient can therefore be switched back to `2.0` in the input without
changing the BC implementation.

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

## Wall-flux discriminator

Repository CI #571 built the exact source head and ran the same configurable
BC at `alpha=2.0` and `alpha=2.5` with `dt=1 ns` to `4 ns`.

```text
alpha=2.0: T_e,max = 3.8453167929391 eV, overshoot = +0.0234767929391 eV
alpha=2.5: T_e,max = 3.8218386527941 eV, overshoot = -1.3472059e-6 eV
alpha=2.0 max energy-balance relative error = 1.9152e-12
alpha=2.5 max energy-balance relative error = 1.7073e-12
```

The transport-matched `alpha=2.5` case removes the wall-tip temperature
overshoot while retaining the conservative energy balance. The `alpha=2.0`
case remains available as a controlled kinetic-closure discriminator.
