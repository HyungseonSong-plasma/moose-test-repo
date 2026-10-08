# Issue #202 — scalar RZ FEM Maxwell M0/M1 baseline

This directory is the first implementation surface for the canonical Maxwell / RF-ICP issue #202.

## Status

```text
PHASE                    = M0/M1 candidate implementation
REPRESENTATION           = scalar axisymmetric E_theta
DISCRETIZATION           = continuous FEM
PHASOR                    = exp(+i omega t), peak amplitude
COIL DRIVE                = prescribed current
COPPER SKIN/PROXIMITY     = OFF
PLASMA FEEDBACK           = OFF in this first discriminator
SCIENTIFIC ACCEPTANCE     = NOT CLAIMED
```

The first runtime target is the M2-B vacuum/source discriminator. Passing this input or CI is not Maxwell scientific acceptance.

## Frozen equation

For constant `mu = mu0`, with the equation multiplied by `mu0`, the solved field is

```text
E_theta = E_real + i E_imag
```

and

```text
-laplacian_RZ(E_theta)
+ E_theta/r^2
+ (i omega mu0 sigma - omega^2 mu0 epsilon) E_theta
= -i omega mu0 J_theta^e
```

For

```text
sigma = sigma_R + i sigma_I
```

define

```text
a = 1/r^2 - omega^2 mu0 epsilon - omega mu0 sigma_I
b = omega mu0 sigma_R
```

so that

```text
L(E_real) + a E_real - b E_imag = S_real
L(E_imag) + a E_imag + b E_real = S_imag
```

with `L = -laplacian_RZ`. For a real impressed-current reference phase,

```text
S_real = 0
S_imag = -omega mu0 J_theta^e
```

The initial vacuum/source case sets `epsilon_r = 1`, `sigma = 0` everywhere. This deliberately isolates geometry, axis regularity, coil normalization, source phase/sign, and the scalar-RZ operator.

## MOOSE implementation map

The initial implementation uses standard scalar FEM objects only:

| Maxwell term | MOOSE route | Notes |
| --- | --- | --- |
| `-laplacian_RZ(E)` | `Diffusion` | RZ coordinate system supplies the axisymmetric measure/operator |
| `a E` | `MatReaction` | supplied as `neg_a = -a` because `MatReaction` carries its documented minus sign |
| real/imag `b` coupling | `MatCoupledForce` | retained even though `b=0` in the first vacuum discriminator |
| impressed coil current | `BodyForce` | three independent block-scoped sources |
| axis regularity | `DirichletBC` | `E_theta=0` at `r=0`; this is regularity, not a wall model |
| outer truncation | `DirichletBC` | zero-field baseline; domain-size sensitivity remains mandatory |

No custom Maxwell kernel or BC is introduced at this stage.

## Existing mesh and coil mapping

The case reuses the existing ASCII Gmsh mesh

```text
experiments/Issue18_qvt_plasma_mapping/qvt.msh
```

with

```text
coord_type    = RZ
rz_coord_axis = Y
```

therefore

```text
r = x
z = y
```

The three coil physical blocks are three separate ring-turn cross sections:

| Block | radial interval [m] | axial interval [m] | cross-section [m^2] |
| --- | ---: | ---: | ---: |
| `coil1` | 0.0495–0.0585 | 0.342–0.360 | 1.62e-4 |
| `coil2` | 0.1125–0.1215 | 0.342–0.360 | 1.62e-4 |
| `coil3` | 0.1710–0.1800 | 0.342–0.360 | 1.62e-4 |

They are interpreted as three physical turns of one series coil. The same current phasor therefore flows through each turn:

```text
I1 = I2 = I3 = I_coil
```

For each turn `k`, the impressed azimuthal current density is normalized by the RZ cross section, not by toroidal volume:

```text
J_theta,k = I_coil / A_k
integral_Ak J_theta,k dA = I_coil
```

There is **no additional factor of three** in an individual turn and **no division by `2*pi*r`**. The RZ FEM volume measure is a separate integration concern.

The input intentionally keeps the three source objects separate:

```text
coil1_current -> block coil1
coil2_current -> block coil2
coil3_current -> block coil3
```

This enables `coil1 only`, `coil2 only`, `coil3 only`, all-three, and targeted sign-reversal negative-mutation discriminators.

## Default source point

The committed baseline uses

```text
frequency = 13.56 MHz
I_peak    = 10 A
```

with peak phasors throughout. If an experimental coil current is supplied as RMS, it must first be converted with

```text
I_peak = sqrt(2) I_rms
```

before using the peak-phasor power convention.

## Validation

Static source/mesh contract:

```bash
python3 experiments/Issue202_maxwell_scalar_fem_m0/check_contract.py
```

Runtime/check-input, from repository root after `physics_app/physics-opt` is available:

```bash
physics_app/physics-opt \
  -i experiments/Issue202_maxwell_scalar_fem_m0/input.i \
  --check-input

physics_app/physics-opt \
  -i experiments/Issue202_maxwell_scalar_fem_m0/input.i
```

The bounded M2 vacuum/source validation now checks:

```text
E_real ~ 0 for real coil current and sigma=0
E_imag != 0
field scales linearly with I_peak at 5/10/20 A
turn-by-turn superposition reproduces the all-three solution
coil2 sign reversal (I,-I,I) reproduces E1-E2+E3
coil2 sign reversal materially changes the spatial field
```

### Accepted bounded runtime evidence

Current linearity and positive-turn superposition:

```text
Actions run: 37823781035
semantic head: 10a0b4b1cd23dc5cfde6fb103051c7d7fe06e07c
max current-linearity relative error: ~3.8e-14
max signed-probe superposition absolute error: ~5.0e-13 V/m
```

Coil2 sign-reversal negative mutation:

```text
Actions run: 37824371343
semantic head: 55445e336eb63f8e8c4fa9a6bb007937b598ed28
(I1,I2,I3) = (I,-I,I)
E_imag_l2 = 17.14724390071
E_real_l2 = 0
```

Signed probes for the sign-reversal case are

| r [m] | all-positive [V/m] | coil2-negative [V/m] |
| ---: | ---: | ---: |
| 0.05 | -58.209951694552 | -7.3352426640216 |
| 0.10 | -92.276646096118 | -12.996755373028 |
| 0.15 | -90.485037974822 | -18.618129221516 |
| 0.20 | -55.955177156375 | -15.657707747501 |

All four probes change materially. The mutated solution also satisfies

```text
E_mut = E1 - E2 + E3
```

with maximum signed-probe absolute mismatch of about `5.0e-13 V/m`.

## Deferred work

Not admitted by this baseline:

- plasma conductivity feedback;
- complex `sigma` validation;
- dielectric/interface reference case;
- copper conductivity, skin effect, or proximity effect;
- voltage/circuit/fixed-power drive;
- conservative RF-power transfer into electron energy;
- mesh-convergence acceptance;
- outer-domain sensitivity acceptance;
- COMSOL / external-reference field-profile equivalence;
- closed-loop ICP coupling.

These remain under issue #202 M1–M5 gates.
