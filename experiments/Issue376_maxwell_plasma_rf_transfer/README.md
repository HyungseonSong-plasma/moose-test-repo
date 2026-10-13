# Issue #376 — Maxwell → plasma RF power transfer

Scientific record for conservative RF-power coupling from the frozen Issue #202 scalar-RZ frequency-domain Maxwell solution into the promoted oxygen-plasma electron-energy model.

## Frozen upstream contract

Issue #202 remains the Maxwell owner. The accepted peak-phasor convention is

```text
E(t) = Re{E_hat exp(+i omega t)}
Q_RF = 0.5 * sigma_R * |E_hat|^2
P_abs = integral_plasma Q_RF dV
```

The frozen standalone reference has `P_abs = 175.81487393245 W`. Reactive conductivity enters the Maxwell field but not collisional RF heating.

## Production representation

The promoted plasma path solves `log_energy` with continuous FEM/LAGRANGE; selected heavy charged transport remains FVM. RF heating is therefore injected directly into the FEM electron-energy equation instead of introducing an obsolete FE→FV→FE projection.

The accepted coupled path is

```text
oxygen plasma state
  -> physical n_e / mean electron energy / pressure
  -> complex Drude conductivity
  -> scalar-RZ frequency-domain Maxwell
  -> Q_RF = 0.5 sigma_R |E_RF|^2
  -> target-side conservative RF-power normalization
  -> separate FEM log_energy RF source
  -> updated oxygen-plasma state
  -> fixed-drive Maxwell feedback
```

Standard MOOSE objects are used for the production coupling (`SolutionUserObject`, `SolutionAux`, `PiecewiseLinearInterpolationMaterial`, `ParsedMaterial`, `MatBodyForce`). No custom C++ was required.

RF heating remains separate from electrostatic electron work; the electrostatic drift/Joule-heating ownership is not silently modified to use `E_ES + E_RF`.

## Final acceptance status

```text
T1 conservative transfer       PASS
T2 spatial transfer            PASS
T3 counterfactuals             PASS
T4 coupling convergence        PASS
T5 power closure               PASS
T6 representative oxygen ICP   PASS
```

### T1–T3

Authoritative exact-head regression:

```text
Actions       38372574448
head          51b5016b41461fc5aace381ec6e148258cd62fbd
artifact      11800162231
artifact sha  189eed72d3185bbe5e74034e053a6dec301112028143f37ea0605453ed79cfa7
```

T1 independent exact TRI3 integration reproduced the frozen Maxwell absorbed power to machine precision and closed the electron-energy unit conversion. T2 independently reconstructed the cross-mesh spatial transfer and obtained approximately `1.01%` complex-field RZ L2 error, `0.68%` `Q_RF` RZ L2 error, and `0.86%` normalized power-shape error, all below the predeclared `2%` gate. T3 closed transfer-off, RF-source-off, `sigma_R=0` reactive-only, and frozen-state deterministic counterfactuals.

## T4 — bounded segregated convergence

T4 used the reduced plasma discriminator before enabling full oxygen chemistry. Each physical backward-Euler step used an unrelaxed Picard loop:

```text
plasma state guess
  -> mobility / collision frequency / complex sigma
  -> frequency-domain Maxwell
  -> conservative RF transfer
  -> one FEM log_energy step from the fixed previous physical state
  -> updated state guess
```

Historical calibration failures are retained rather than retroactively reclassified:

- T4-v1 (`38375574743`) failed the original 8-iteration cap despite an asymptotic Picard contraction near `0.142`.
- T4-v2 (`38376764298`) closed Picard under the revised 12-iteration budget but failed the unchanged `<0.5%` temporal-accuracy gate.
- T4-v3 (`38378567904`, head `f5878affb01fd7c86b4718bfb9b5a78d06ca8197`) moved only the timestep triplet into the asymptotic regime and passed the unchanged gates. Medium→fine final-state difference was about `0.29185%`; refinement difference ratio was about `0.5020`.

## T5 — power closure

Authoritative run:

```text
Actions  38384990679
head     b182fd7d99a8f79756de509c864479bf64a21af6
artifact 11805137438
```

Representative evidence:

```text
Maxwell P_abs                    = 34.782732117 W
raw mapping defect               = 0.1824681 %
deposited / Maxwell closure      = 0
source-unit relative closure     = 2.25e-15
electron-energy inventory error  = 3.44e-13
source-off inventory drift       = 0
```

The RF source has one explicit owner and remains separate from electrostatic Joule heating.

## T6 — representative full oxygen ICP, 1000 W

The first T6 attempt exposed two real integration defects rather than relaxing the gates:

1. nonlinear `log(n_e)` remapping biased spatial conductivity and produced a `3.0945%` raw remesh power defect;
2. deposition normalization used the independent reconstruction rather than the actual MOOSE target raw integral, leaving a `0.2369%` closure residual.

T6-v2 corrected both by transferring physical electron density / mean energy before constitutive evaluation and by using the actual MOOSE target raw integral as the deposition-normalization owner. The independent reconstruction remains a discriminator only.

The first Maxwell state is calibrated to `1000 W` absorbed plasma power. The resulting source amplitude is then held fixed for the feedback Maxwell solve; the second absorbed power is therefore a genuine plasma-response metric, not a second fixed-power renormalization.

Authoritative exact-head result:

```text
Actions        38394816028
head           ce4d36b6b4a86c9446d646aaeeb4b19e6da3b616
artifact       11815280638
artifact sha   1331ecc77040317089b194b5365d25a93a888b032611b218094daa28f974dc05
classification T6_REPRESENTATIVE_ICP_V2_PASS
failures       []
```

Key T6-v2 evidence:

```text
target absorbed power              = 1000.0 W
Maxwell1 P_abs                      = 999.99999999998 W
target power relative error        = 2.00e-14
MOOSE target raw power             = 1000.2556940662 W
MOOSE target scaled power          = 999.99999999997 W
deposited relative closure         = 1.00e-14
source-unit relative closure       = 1.32e-14
independent target raw power       = 997.891035411457 W
raw spatial-transfer defect        = 0.210896 %
effective peak coil current        = 74.9559809638 A
transport-table clamp fraction     = 0
```

Fixed-drive feedback after one `1 ns` RF-heated full-physics step:

```text
Maxwell P_abs        1000.0000 -> 998.9873 W
power change         0.10127 %
Maxwell field L2     351.396734 -> 351.400467
field change         1.06e-5
electron mean-energy field relative change = 14.65 %
```

The full-physics gate also confirmed finite positive electron state, required oxygen FVM variables, dielectric surface-charge coupling, physical state mapping, and RF/electrostatic heating separation.

## Scope closure

Issue #376 closes the conservative Maxwell→plasma RF transfer, bounded segregated coupling, power closure, and representative 1000 W oxygen-ICP feedback scope. Copper skin/proximity effects, external matching circuitry, and a continuous fixed-power controller remain separate future work.

The temporary `issue376-*-once.yml` workflows were intentionally removed before merge; the experiment drivers and acceptance record remain under this directory.
