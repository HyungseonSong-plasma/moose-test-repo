# Issue #376 — Maxwell → plasma RF power transfer

Active development surface for conservative RF-power coupling from the frozen
Issue #202 scalar-RZ Maxwell solution into the current plasma electron-energy
equation.

## Upstream contract

Issue #202 is frozen. Its accepted peak-phasor heating law is

```text
Q_RF = 0.5 * sigma_R * (E_real^2 + E_imag^2)
P_abs = integral_plasma Q_RF dV
```

with accepted science head
`fb27e232924a0ee11010669eff287d9b953f1a31`, Actions run `37836361274`,
artifact `11575123517`, and `P_abs = 175.81487393245 W`.

## Representation synchronization

The original #376 wording assumed that the electron-energy destination would
remain cell-centered FVM. The current promoted plasma line instead solves
`log_energy` with continuous FEM/LAGRANGE, while selected heavy charged
transport remains FVM.

Therefore the production RF-heating path must not introduce an unnecessary
FE -> FV -> FE projection. The preferred current architecture is:

```text
Maxwell E_real/E_imag : FEM
Q_RF material         : quadrature-point material on plasma
electron log_energy   : FEM
source injection      : same-mesh FEM volume source
```

The conservative cell-average construction is retained as an independent
oracle and as the required discriminator should an FV destination be used
later.

No custom C++ is authorized by this directory. Standard MOOSE
`MatBodyForce`/`ADMatBodyForce` is the first production source-injection
candidate.

## T1A — independent conservative transfer oracle

`conservative_rf_power_reference.py` reads the upstream Maxwell Exodus field
and integrates each TRI3 plasma element exactly in RZ.

For P1 fields,

```text
E_h = sum_i E_i lambda_i
r   = sum_i r_i lambda_i
```

so `r * |E_h|^2` is a degree-3 polynomial. The script evaluates its element
integral analytically from barycentric moments:

```text
P_K = 2*pi * integral_K r Q_RF dA
V_K = 2*pi * integral_K r dA
Q_K = P_K / V_K
```

and independently verifies

```text
sum_K Q_K V_K = integral_plasma Q_RF dV.
```

It also converts the source into the canonical log-molar electron-energy
units,

```text
S_RF [eV mol/(m^3 s)] = Q_RF [W/m^3] / F
F = N_A e = 96485.33212331001 C/mol.
```

### Evidence on the frozen #202 artifact

`T1A_REFERENCE_EVIDENCE.json` records:

```text
plasma TRI3 cells                    = 2348
exact independent FE integral        = 175.81487393245106 W
MOOSE P_abs                          = 175.81487393245 W
independent/MOOSE relative mismatch  = 5.9813e-15

conservative cell sum                = 175.81487393245106 W
cell-average closure                 = 0.0
energy-unit reconstructed power      = 175.81487393245106 W
energy-unit closure                  = 0.0

centroid-point negative mutation     = 175.1021229861442 W
centroid relative power defect       = 4.053985e-3
```

The centroid mutation is intentionally non-conservative and is rejected by
the oracle. The lossless, reactive-only, and RF-source-off upstream
counterfactuals all reconstruct zero deposited power.

## Status

```text
T1A independent conservative oracle     PASS
T1B production MOOSE source injection   NEXT
T1 full acceptance                      NOT YET CLAIMED
T2 spatial transfer                     NOT YET STARTED
T3+                                     NOT YET STARTED
```

T1B must use the current dielectric baseline and prove that the actual
electron-energy RF source integrates back to the Maxwell absorbed power
without modifying the electrostatic Joule-work path.
