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
