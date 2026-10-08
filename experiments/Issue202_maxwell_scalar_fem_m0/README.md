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
OUTER E_THETA=0           = NOT ADMITTED at the committed compact boundary
SCIENTIFIC ACCEPTANCE     = NOT CLAIMED
```

The first runtime target is the M2 vacuum/source validation family. Passing an input or CI job is not Maxwell scientific acceptance.

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
| outer truncation candidate | `DirichletBC` | compact zero-field boundary failed M2-F domain sensitivity; not admitted |

No custom Maxwell kernel or BC is introduced at this stage.

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

They are interpreted as three physical turns of one series coil. The same current phasor flows through each turn:

```text
I1 = I2 = I3 = I_coil
J_theta,k = I_coil / A_k
integral_Ak J_theta,k dA = I_coil
```

There is no additional factor of three in an individual turn and no division by `2*pi*r`. The input keeps the three source objects separate so single-turn, superposition, and sign-reversal discriminators remain possible.

## Default source point

The committed baseline uses

```text
frequency = 13.56 MHz
I_peak    = 10 A
```

with peak phasors throughout. If an experimental current is RMS, convert with `I_peak = sqrt(2) I_rms` before using the peak-phasor power convention.

## Validation

Static source/mesh contract:

```bash
python3 experiments/Issue202_maxwell_scalar_fem_m0/check_contract.py
```

Runtime/check-input, from repository root after `physics_app/physics-opt` is available:

```bash
physics_app/physics-opt -i experiments/Issue202_maxwell_scalar_fem_m0/input.i --check-input
physics_app/physics-opt -i experiments/Issue202_maxwell_scalar_fem_m0/input.i
```

The bounded M2 vacuum/source validation now checks:

```text
E_real ~ 0 for real coil current and sigma=0
E_imag != 0
field scales linearly with I_peak at 5/10/20 A
turn-by-turn superposition reproduces the all-three solution
coil2 sign reversal (I,-I,I) reproduces E1-E2+E3
coil2 sign reversal materially changes the spatial field
global h-refinement levels 0/1/2 converge for E_imag L2 and four signed probes
outer-domain sensitivity challenges the compact E_theta=0 truncation
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
max signed-probe basis mismatch: ~5.0e-13 V/m
```

Global mesh-convergence discriminator:

```text
Actions run: 37825300568
semantic head: 33547b7cc4d2431eedceef5610c91c4fc64dca4c
acceptance gate: medium->fine relative change < 1% for E_imag_l2 and four signed probes
```

| Level | Elements | DOFs | `E_imag_l2` |
| ---: | ---: | ---: | ---: |
| 0 | 3,951 | 4,100 | 48.029611050537 |
| 1 | 15,804 | 16,100 | 48.108814494584 |
| 2 | 63,216 | 63,806 | 48.130698802257 |

For the global L2 observable, the relative change decreases from `0.1646%` at level 0->1 to `0.04547%` at level 1->2, with observed order about `1.86`.

Fine/medium signed-probe relative changes are:

| Probe | level 1 -> 2 relative change |
| --- | ---: |
| `r=0.05 m` | 0.02229% |
| `r=0.10 m` | 0.004128% |
| `r=0.15 m` | 0.01360% |
| `r=0.20 m` | 0.02068% |

`E_imag_min` also changes by only `0.778%` from medium to fine. `E_imag_max` is retained as diagnostic-only because it approaches zero and therefore has an ill-conditioned relative-error denominator; it is not used as a mesh-convergence acceptance observable.

The committed default remains `mesh_refine = 0`. Higher levels are validation overrides rather than a silent production-mesh change.

### M2-F outer-domain sensitivity — FAIL for compact zero-field truncation

The existing mesh contains top/right/bottom exterior-buffer blocks. The M2-F discriminator preserves all device, plasma, quartz, and coil geometry and stretches only those exterior buffers while retaining `E_theta=0` on the new far boundary.

Frozen buffer/device interfaces:

```text
r_inner        = 0.243 m
z_bottom_inner = 0.018 m
z_top_inner    = 0.432 m
```

The tested outer boundaries were:

| factor | r_max [m] | z_min [m] | z_max [m] |
| ---: | ---: | ---: | ---: |
| 1 | 0.2565 | 0.000 | 0.450 |
| 2 | 0.2700 | -0.018 | 0.468 |
| 4 | 0.2970 | -0.054 | 0.504 |
| 8 | 0.3510 | -0.126 | 0.576 |
| 16 | 0.4590 | -0.270 | 0.720 |
| 32 | 0.6750 | -0.558 | 1.008 |

Outer-domain acceptance uses signed field probes at fixed physical coordinates, not global `L2`, because the integration volume changes with the domain.

Runtime evidence:

```text
Actions run: 37827058065
semantic head: 3d65abcab027d602bc2b52c70adfe058bd47692e
classification: FINITE_DIRICHLET_TAIL_NOT_CONVERGED
```

Key results:

```text
max fixed-probe relative change, factor 1 -> factor 32 = 60.12%
max fixed-probe relative change, factor 16 -> factor 32 = 5.61%
factor-32 coarse -> global h-refined cross-check      = 7.34%
```

Selected mid-plane values illustrate the size of the compact-boundary effect:

| probe | factor 1 [V/m] | factor 16 [V/m] | factor 32 coarse [V/m] | factor 32 refined [V/m] |
| --- | ---: | ---: | ---: | ---: |
| `r=0.05,z=0.225` | -58.2100 | -80.3574 | -79.3927 | -82.4821 |
| `r=0.10,z=0.225` | -92.2766 | -135.9565 | -134.3792 | -140.1872 |
| `r=0.15,z=0.225` | -90.4850 | -154.9225 | -153.3767 | -161.0935 |
| `r=0.20,z=0.225` | -55.9552 | -140.6816 | -140.3019 | -149.1702 |

Therefore the committed compact `E_theta=0` outer boundary is **not admitted as a physically innocuous truncation**. It materially suppresses the internal inductive field. The factor-32 stretched mesh is itself under-resolved, so factor 32 is not adopted as a replacement production domain either.

The next boundary gate is standard-capability-first: determine whether the current framework provides an appropriate open/infinite/Robin/absorbing exterior treatment, or build a properly resolved enlarged exterior mesh before reconsidering a finite zero-field boundary. No custom Maxwell BC is admitted until the standard capability census is exhausted.

## Deferred / blocked work

Not admitted by this baseline:

- compact `E_theta=0` outer truncation as a validated far-field boundary;
- replacement outer-boundary treatment, pending capability census and V&V;
- plasma conductivity feedback;
- complex `sigma` validation;
- dielectric/interface reference case;
- copper conductivity, skin effect, or proximity effect;
- voltage/circuit/fixed-power drive;
- conservative RF-power transfer into electron energy;
- COMSOL / external-reference field-profile equivalence;
- closed-loop ICP coupling.

These remain under issue #202 M1–M5 gates.
