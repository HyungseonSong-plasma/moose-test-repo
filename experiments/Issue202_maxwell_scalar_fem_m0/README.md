# Issue #202 — scalar RZ FEM Maxwell M0/M1 baseline

This directory is the first implementation surface for the canonical Maxwell / RF-ICP issue #202.

## Status

```text
PHASE                    = M0/M1 candidate implementation + bounded M2 V&V
REPRESENTATION           = scalar axisymmetric E_theta
DISCRETIZATION           = continuous FEM
PHASOR                    = exp(+i omega t), peak amplitude
COIL DRIVE                = prescribed current
CHAMBER WALL              = physical conductor, E_theta = 0 (PEC baseline)
COPPER SKIN/PROXIMITY     = OFF in the chamber baseline
PLASMA FEEDBACK           = OFF in standalone Maxwell V&V
SCIENTIFIC ACCEPTANCE     = NOT CLAIMED
```

Passing an input or CI job is not Maxwell scientific acceptance.

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

For `sigma = sigma_R + i sigma_I`, define

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

The first vacuum/source case sets `epsilon_r = 1`, `sigma = 0` everywhere and isolates geometry, axis regularity, coil normalization, source phase/sign, and the scalar-RZ operator.

## Canonical boundary semantics

The current `qvt.msh` domain is the physical chamber, not an arbitrary far-field truncation.

```text
axis r=0:
    E_theta = 0
    reason = azimuthal-field regularity, E_theta = O(r)

outer_right / outer_bottom / outer_top:
    E_theta = 0
    reason = physical conducting chamber wall (PEC baseline)

internal conformal interfaces:
    no explicit BC
```

For the scalar azimuthal RF field, `E_theta` is tangential to the conducting chamber wall. The PEC condition `n x E = 0` therefore gives `E_theta = 0` on the chamber boundary. This boundary is not moved in canonical chamber calculations.

No custom Maxwell kernel or BC is introduced at this stage.

## MOOSE implementation map

| Maxwell term | MOOSE route | Notes |
| --- | --- | --- |
| `-laplacian_RZ(E)` | `Diffusion` | RZ coordinate system supplies the axisymmetric measure/operator |
| `a E` | `MatReaction` | supplied as `neg_a = -a` because `MatReaction` carries its documented minus sign |
| real/imag `b` coupling | `MatCoupledForce` | standard composition for complex conductivity |
| impressed coil current | `BodyForce` | three independent block-scoped sources |
| axis regularity | `DirichletBC` | `E_theta=0` at `r=0`; not a wall model |
| conducting chamber | `DirichletBC` | physical PEC baseline, `E_theta=0` |

## Existing mesh and coil mapping

The case reuses `experiments/Issue18_qvt_plasma_mapping/qvt.msh` with

```text
coord_type    = RZ
rz_coord_axis = Y
r = x
z = y
```

The three coil physical blocks are separate ring-turn cross sections:

| Block | radial interval [m] | axial interval [m] | cross-section [m^2] |
| --- | ---: | ---: | ---: |
| `coil1` | 0.0495–0.0585 | 0.342–0.360 | 1.62e-4 |
| `coil2` | 0.1125–0.1215 | 0.342–0.360 | 1.62e-4 |
| `coil3` | 0.1710–0.1800 | 0.342–0.360 | 1.62e-4 |

They are interpreted as three physical turns of one series coil:

```text
I1 = I2 = I3 = I_coil
J_theta,k = I_coil / A_k
integral_Ak J_theta,k dA = I_coil
```

There is no additional factor of three in an individual turn and no division by `2*pi*r`.

## Default source point

```text
frequency = 13.56 MHz
I_peak    = 10 A
```

Peak phasors are used throughout. RMS experimental currents must be converted with `I_peak = sqrt(2) I_rms` before using the peak-phasor power convention.

## Accepted bounded runtime evidence

### Source normalization, phase, linearity, and superposition

```text
baseline semantic head: f568cec35b70dd1530e066df460e4451ab317af5
baseline Actions run:   37822805237
E_real_l2 = 0
E_imag_l2 = 48.02961

linearity/superposition semantic head: 10a0b4b1cd23dc5cfde6fb103051c7d7fe06e07c
Actions run: 37823781035
5/10/20 A current-linearity max relative error: ~3.8e-14
E(all) = E1 + E2 + E3 max signed-probe mismatch: ~5.0e-13 V/m

coil2 sign-reversal semantic head: 55445e336eb63f8e8c4fa9a6bb007937b598ed28
Actions run: 37824371343
(I1,I2,I3)=(I,-I,I) gives E_mut = E1-E2+E3
max signed-probe basis mismatch: ~5.0e-13 V/m
```

### Global mesh convergence — PASS

```text
semantic head: 33547b7cc4d2431eedceef5610c91c4fc64dca4c
Actions run: 37825300568
```

| Level | Elements | DOFs | `E_imag_l2` |
| ---: | ---: | ---: | ---: |
| 0 | 3,951 | 4,100 | 48.029611050537 |
| 1 | 15,804 | 16,100 | 48.108814494584 |
| 2 | 63,216 | 63,806 | 48.130698802257 |

Medium-to-fine `E_imag_l2` change is `0.04547%`; all four signed-probe changes are below `0.023%`. Observed L2 convergence order is about `1.86`. The committed chamber baseline remains `mesh_refine=0`; refinement levels are validation overrides.

## Correction: previous outer-domain stretch is NOT an M2-F failure

A previous diagnostic stretched the existing top/right/bottom regions by factors up to 32 while retaining `E_theta=0` on the moved boundary. That diagnostic produced large internal-field changes, but the interpretation as a numerical outer-truncation sensitivity test was invalid.

The reason is physical: `outer_right`, `outer_bottom`, and `outer_top` represent the conducting chamber wall. Moving them changes the physical chamber geometry rather than merely moving an artificial far-field boundary.

Therefore:

```text
previous classification FINITE_DIRICHLET_TAIL_NOT_CONVERGED = RETRACTED
M2-F FAIL claim from chamber-wall movement                 = RETRACTED
canonical chamber-wall E_theta=0                           = RETAINED
```

The historical stretch data remain provenance only and are not used to accept or reject the physical chamber BC.

Open-space `EMRobinBC`, infinite-element, or free-space Green-function treatments may still be useful for separate standalone open-domain reference problems, but they are not replacement production BCs for this conducting-chamber model.

## Next standalone material V&V

The next gate is the M2 material ladder:

```text
M2-C prescribed conducting medium / skin-depth case
M2-D dielectric/material-interface case
```

These tests must validate the real/imaginary conductivity coupling and material coefficient placement independently of plasma feedback before the chamber plasma is assigned a physical conductivity model.

## Deferred work

- plasma-state -> conductivity feedback;
- dielectric/interface reference acceptance;
- prescribed-conductivity / skin-depth acceptance;
- copper skin/proximity in the physical coil conductor;
- voltage/circuit/fixed-power drive;
- conservative RF-power transfer into electron energy;
- COMSOL / external-reference chamber field-profile equivalence;
- closed-loop ICP coupling.

These remain under issue #202 M1–M5 gates.
