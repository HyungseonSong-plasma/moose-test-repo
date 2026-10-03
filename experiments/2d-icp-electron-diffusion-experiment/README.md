# 2d-icp-electron-diffusion-experiment

Reusable diagnostic baseline for the real-QVT 2-D ICP plasma geometry.

## Purpose

Use this experiment when a more complete 2-D ICP electron/Poisson/coupled case develops an unexplained profile or fails to converge.  The baseline intentionally removes every electron coupling except particle diffusion and thermal wall loss.

The solved equation is

```text
d(c_e)/dt - div(D_e grad(c_e)) = 0
```

with a uniform initial electron density

```text
n_e(t=0) = 1.0e16 1/m^3
```

and fixed mean electron energy

```text
mean electron energy = 5.73276 eV
```

## Transport contract

Electron energy is not a solved variable.  Instead,

```text
electron_energy_density_eV_m3 = electron_density_m3 * 5.73276 eV
```

is constructed as a derived functor and passed to `PhysicsElectronClosureMaterial`.

Therefore the closure still executes the production path

```text
fixed mean energy
  -> electron_moments.txt lookup
  -> reduced diffusion D_e*N
  -> divide by neutral number density
  -> physical electron_diffusion [m^2/s]
```

The diffusivity is constant for this baseline because pressure, gas temperature, and mean electron energy are fixed, but the lookup-table architecture is preserved exactly for later promotion.

## Boundary contract

All named plasma boundaries use `PhysicsFVElectronGroundedSheathCollectionBC`.

The BC receives

```text
potential = zero_phi = 0 V
```

so the sheath suppression factor is unity.  This is deliberately the pure thermal quarter-Maxwellian electron collection branch.  There is no Poisson solve and no volume electrostatic drift.

The RZ symmetry axis is not assigned the wall-loss BC.

## Physics deliberately absent

```text
Poisson                  OFF
electron electrostatic drift OFF
electron energy equation OFF
electron reactions       OFF
heavy-species equations  ABSENT
volumetric sources       OFF
```

## Frozen reusable assets

This directory contains frozen copies of the accepted real-QVT ICP mesh and electron transport table so the diagnostic can be executed independently.

```text
qvt.msh
  source: experiments/Issue91_real_qvt_r3/r3_e0/qvt.msh
  sha256: a98521af2c106137f9635fe7e2c5ba9b0fd408e17c62eb7c6d3f7c1fff65a03e

electron_moments.txt
  source: experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt
  sha256: 994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387
```

## Run

From the repository root:

```bash
python3 bin/physics.py test experiments/2d-icp-electron-diffusion-experiment \
  --qpx /path/to/physics-opt
```

or directly from this directory:

```bash
/path/to/physics-opt -i input.i
python3 check.py
```

The run produces `electron_diffusion.e`, `electron_diffusion.csv`, and a final element profile CSV.  The checker verifies only baseline invariants: fixed energy, positive table-derived diffusivity, positive density, nonzero thermal wall loss, and decreasing total electron inventory.

## Escalation sequence

When using this as a 2-D ICP troubleshooting inventory item, add physics back one layer at a time:

```text
1. this diffusion-only baseline
2. + prescribed electrostatic drift
3. + Poisson with frozen heavy charge
4. + electron energy equation
5. + electron reactions
6. + heavy-species evolution / full coupling
```

A failure should be assigned to the first layer at which the accepted baseline changes unexpectedly.


## Execution baseline

The stabilization run uses:

```text
dt        = 1.0e-9 s
num_steps = 4
end_time  = 4.0e-9 s
```

The input is first required to pass real `physics-opt --check-input`.  One subsequent runtime is then used to evaluate transport lookup, thermal wall loss, electron inventory balance, spatial profile, and Exodus output together.


## Stabilization evidence

Repository CI run `37024044297` at head
`fe5e532317258f30873185783e9fcf7bddb276ec` establishes this experiment as
`STABLE_REUSABLE_BASELINE` for the bounded diffusion-only physics scope.

```text
physics-opt --check-input       PASS
dt                              1.0e-9 s
physical steps                  4
end time                        4.0e-9 s
all nonlinear solves            PASS, 3 Newton updates per step
fixed mean electron energy      5.73276 eV
D_e from transport table        20628.592493561 m^2/s
initial wall rate               4.900943951004e-3 mol/s
initial electron inventory      8.3205870186091e-10 mol
final electron inventory        8.1417261905889e-10 mol
inventory loss over 4 ns        2.149617900998 %
final n_e minimum               7.9505488461108e15 1/m^3
final n_e maximum               9.9999999721474e15 1/m^3
sqrt(D_e t) at 4 ns             9.083742 mm
```

The 5.73276 eV transport-table row supplies `D_e*N=6.64e24`.  With
`p=1.333223684 Pa` and `T_g=300 K`, the neutral density is
`3.218833278166041e20 1/m^3`, so the runtime diffusivity exactly matches
`(D_e*N)/N_g`.

The zero-potential thermal wall BC is also quantitatively closed.  The frozen
geometry has total named thermal-loss area `0.9023470915199818 m^2`; the
quarter-Maxwellian law at the fixed mean energy predicts the observed initial
wall particle rate to floating-point precision.

At every physical timestep the backward-Euler particle balance

```text
(I_e[n] - I_e[n-1]) / dt + wall_particle_rate[n] = 0
```

closes with maximum relative imbalance `6.84e-12`.

The final 2-D field is qualitatively correct for pure diffusion plus absorbing
thermal boundaries: the bulk remains essentially at `1e16 1/m^3`, while the
outer wall, wafer, cover, inlet/outlet, and other thermal-loss boundaries show
smooth depletion over the expected diffusion penetration scale.  At
`z ~= 0.20 m`, the radial profile is flat from the axis through the bulk and
falls only near the outer radial wall.  No unphysical interior maximum or
density overshoot appears.

This qualification does not cover electrostatic drift, Poisson, electron
energy evolution, reactions, or heavy-species coupling.


## Template contract

The qualified runtime input is frozen byte-for-byte as
`input.template.i`. The file `simple_case_template.json` declares the
template input, generated input name, and reusable assets.

To create a new experiment from this baseline:

```bash
python3 bin/physics.py simple-case create \
  electron-diffusion-experiment \
  experiments/my-derived-electron-case
```

To scaffold the same baseline and then replace only the input:

```bash
python3 bin/physics.py simple-case create \
  electron-diffusion-experiment \
  experiments/my-derived-electron-case \
  --input /path/to/new_input.i
```

The new directory contains `qvt.msh`, `electron_moments.txt`,
`input.i`, `test.json`, and `template_origin.json`. The origin record
sets `qualification_inherited=false`; the derived input must be validated
independently.
