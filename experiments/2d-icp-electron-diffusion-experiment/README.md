# 2d-icp-electron-diffusion-experiment

Reusable diagnostic baseline for the real-QVT 2-D ICP plasma geometry.

## Purpose

This is the smallest 2-D ICP electron case that evolves both electron particles
and electron energy.  It intentionally removes electrostatic drift, Poisson,
reactions, Joule heating, volumetric energy sources, and heavy-species
evolution so geometry, transport lookup, particle diffusion, energy diffusion,
and thermal wall losses can be isolated together.

The solved conservative states are

```text
d(c_e)/dt       - div(D_e(mean_en) grad(c_e))             = 0
d(c_epsilon)/dt - div(D_epsilon(mean_en) grad(c_epsilon)) = 0
```

with

```text
n_e(t=0)    = 1.0e16 1/m^3
mean_en(t=0)= 5.73276 eV
c_epsilon   = c_e * mean_en
```

Here `c_e` is electron molar concentration and `c_epsilon` is conservative
electron-energy density in eV mol/m^3.

## Mean-energy and transport contract

`mean_en` is no longer frozen.  The production closure receives

```text
electron_number_density      = N_A * c_e
electron_energy_density      = N_A * c_epsilon
mean_en_solved               = electron_energy_density / electron_number_density
                             = c_epsilon / c_e
```

and then performs the normal `electron_moments.txt` lookup:

```text
mean_en_solved
  -> interpolate D_e * N
  -> divide by neutral number density
  -> electron_diffusion [m^2/s]

mean_en_solved
  -> interpolate D_e * N
  -> (5/3) factor
  -> electron_energy_diffusion [m^2/s]
```

The lookup uses `lookup_bounds_policy = error`; a solved mean energy outside
the table range is therefore a hard runtime failure rather than a silent clamp.

## Boundary contract

Every named plasma boundary uses the same grounded thermal/sheath branch for
both conserved equations.

Particle loss:

```text
PhysicsFVElectronGroundedSheathCollectionBC
variable = log_e
mean_electron_energy = mean_en_solved
potential = zero_phi
```

Energy loss:

```text
PhysicsFVElectronGroundedSheathEnergyBC
variable = c_epsilon
electron_density = c_e_molar
mean_electron_energy = mean_en_solved
potential = zero_phi
molar_energy_state = true
```

Because `zero_phi = 0 V`, sheath suppression is unity.  The particle BC is
the thermal quarter-Maxwellian collection law and the energy BC removes the
same collected primary population with energy `2 T_e = (4/3) mean_en`.

The RZ symmetry axis is not assigned either wall-loss BC.

## Physics deliberately absent

```text
electron electrostatic drift  OFF
Poisson                       OFF
electron reactions            OFF
Joule heating                 OFF
volumetric energy sources     OFF
heavy-species equations       ABSENT
```

## Frozen reusable assets

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

The bounded baseline uses

```text
dt        = 1.0e-9 s
num_steps = 4
end_time  = 4.0e-9 s
```

## Current qualification

Repository CI **#538**, run `37032506883`, at exact physics/configuration head
`e2070e36c8d26172dfbf4ec08afbb77ddf9d4cc9` establishes the solved-energy
baseline.

```text
static/simple-case inventory              PASS
physics-opt --check-input                 PASS
4-step real physics-opt runtime           PASS
particle conservation                     PASS
electron-energy conservation              PASS
local mean_en -> D_e table lookup          PASS

initial mean_en                            5.73276 eV
final mean_en average                      5.691524637256 eV
final mean_en range                        5.534551394882 .. 5.767975189409 eV

initial D_e                                20628.592493561 m^2/s
final average D_e                          20579.931928146 m^2/s
final local D_e range                      20394.709196308 .. 20662.419063281 m^2/s
max local lookup relative error            2.69e-14

max particle balance relative error        3.46e-12
max energy balance relative error          1.92e-12
```

The important result is that diffusivity is no longer a fixed scalar: the
solved mean-energy field produces a spatially varying `D_e`, and the checker
recomputes the table interpolation independently for every sampled final cell.

## Template contract

The qualified runtime input is frozen byte-for-byte as `input.template.i`.
The file `simple_case_template.json` declares the input template and frozen
assets.

```bash
python3 bin/physics.py simple-case create \
  electron-diffusion-experiment \
  experiments/my-derived-electron-case
```

A generated case copies `qvt.msh`, `electron_moments.txt`, and the solved
particle+energy input.  Its `template_origin.json` still sets
`qualification_inherited=false`; changing the generated input requires
independent validation.

## Escalation sequence

Starting from this baseline, add the remaining coupling layers one at a time:

```text
1. particle diffusion + solved energy diffusion          <- this baseline
2. + prescribed electrostatic drift
3. + Poisson with frozen heavy charge
4. + electron-energy drift / Joule work
5. + electron reactions / inelastic energy sources
6. + heavy-species evolution / full coupling
```

A failure should be assigned to the first added layer at which the accepted
baseline changes unexpectedly.
