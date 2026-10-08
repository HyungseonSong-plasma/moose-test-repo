# Issue #202 — scalar RZ FEM Maxwell M0/M1 baseline

This directory is the bounded standalone Maxwell implementation and V&V surface completed under issue #202.

## Final status

```text
REPRESENTATION           = scalar axisymmetric E_theta
DISCRETIZATION           = continuous FEM
PHASOR                    = exp(+i omega t), peak amplitude
COIL DRIVE                = prescribed current
CHAMBER WALL              = physical conductor, E_theta = 0 (PEC baseline)
COPPER SKIN/PROXIMITY     = OFF in the chamber baseline
PLASMA FEEDBACK           = OUT OF SCOPE HERE
STANDALONE MAXWELL M2     = CLOSED / ACCEPTED FOR THIS BOUNDED SCOPE
NEXT WORK                 = separate plasma-transfer issue
```

The bounded scope completed here validates the scalar-RZ Maxwell realization, prescribed complex material response, and RF absorbed-power expression. It does **not** claim full coupled ICP scientific acceptance.

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

For the scalar azimuthal RF field, `E_theta` is tangential to the conducting chamber wall. The PEC condition `n x E = 0` therefore gives `E_theta = 0` on the chamber boundary.

## Coil normalization

The three named RZ coil blocks are interpreted as three physical turns of one series coil:

```text
I1 = I2 = I3 = I_coil
J_theta,k = I_coil / A_k
integral_Ak J_theta,k dA = I_coil
```

There is no additional factor of three in an individual turn and no division by `2*pi*r`.

Default source:

```text
frequency = 13.56 MHz
I_peak    = 10 A
```

## Accepted bounded V&V evidence

### Source normalization / phase / superposition

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

### Global chamber mesh convergence — PASS

```text
semantic head: 33547b7cc4d2431eedceef5610c91c4fc64dca4c
Actions run: 37825300568
```

| Level | Elements | DOFs | `E_imag_l2` |
| ---: | ---: | ---: | ---: |
| 0 | 3,951 | 4,100 | 48.029611050537 |
| 1 | 15,804 | 16,100 | 48.108814494584 |
| 2 | 63,216 | 63,806 | 48.130698802257 |

Medium-to-fine `E_imag_l2` change is `0.04547%`; all four signed-probe changes are below `0.023%`. Observed L2 convergence order is about `1.86`.

### M2-C conducting-cylinder / skin-depth — PASS

```text
semantic head: c9ec4d6d3753701f557a88cf37a7ed7da4fba83f
Actions run: 37829518687
```

At 13.56 MHz with `sigma=100 S/m`, the exact Bessel `J1` solution is matched to `1.2068e-4` maximum complex relative error on the refined mesh (`0.0121%`). This validates the scalar-RZ geometric term, conductivity coupling, and phasor sign convention.

### M2-D dielectric/material interface — PASS

The independent two-layer Helmholtz case with `epsilon_r: 1 -> 4` and no explicit interface BC matches the transfer-matrix analytical solution to `4.6470e-6` maximum relative error on the refined mesh (`0.000465%`).

### M2-G prescribed-material chamber cross-solver equivalence — PASS

```text
semantic head: 915c531d83eaf270f634ae9c73aaccf4f96e6390
Actions run: 37832228877
```

Frozen chamber validation coefficients include plasma `sigma = 5 - 10 i S/m`, cover `epsilon_r=3.6`, wafer `12.5`, and focus ring `8`. MOOSE is compared against an independently assembled complex scalar-RZ H1 FEM solver on the same mesh.

Maximum discrepancies:

```text
complex field relative error = 4.1418e-6
magnitude relative error     = 4.0054e-6
phase error                  = 6.0408e-5 deg
```

### RF absorbed-power gate — PASS

```text
semantic head: fb27e232924a0ee11010669eff287d9b953f1a31
Actions run: 37836361274
artifact ID: 11575123517
```

Peak-phasor heating is

```text
Q_RF = 0.5 * sigma_R * (E_real^2 + E_imag^2)
P_abs = integral_plasma Q_RF dV
      = 2*pi * integral_plasma r * Q_RF dr dz
```

For prescribed `sigma = 5 - 10 i S/m`, 13.56 MHz, and 10 A peak:

```text
MOOSE P_abs       = 175.81487393245 W
independent P_abs = 175.81488589464578 W
relative mismatch = 6.8039e-8
```

Counterfactuals:

```text
sigma_R=sigma_I=0                 -> nonzero RF field, P_abs=0
sigma_R=0, sigma_I=-10 S/m        -> nonzero RF field, P_abs=0
source_scale=0                    -> E=0, P_abs=0
```

This confirms that `sigma_R` is dissipative while `sigma_I` is reactive in the adopted convention.

## Historical chamber-wall stretch diagnostic

A previous diagnostic moved the physical top/right/bottom chamber walls and was initially misclassified as an outer-truncation sensitivity test. That classification was retracted because moving those walls changes the physical chamber geometry. The historical data remain provenance only and do not invalidate the canonical PEC chamber BC.

## Handoff boundary

Issue #202 stops here. The following are intentionally deferred to a separate issue:

- conservative Maxwell-FE `Q_RF` -> plasma electron-energy transfer;
- FE/FV conservation invariant;
- coupled `plasma state -> sigma -> Maxwell -> Q_RF -> electron energy` loop;
- transfer-off / RF-off counterfactuals;
- coupled timestep/fixed-point convergence;
- full ICP power closure and representative oxygen-plasma validation.

COMSOL chamber-profile equivalence may be added later as another independent reference, but is not required to close this bounded standalone Maxwell work package.
