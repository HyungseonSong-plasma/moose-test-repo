# Issue #202 — RF absorbed-power validation

## Frozen convention

Peak phasors with `exp(+i omega t)` are used. The collisional RF heating density is

```text
Q_RF = 0.5 * sigma_R * (E_real^2 + E_imag^2)   [W/m^3]
```

and the axisymmetric absorbed power is

```text
P_abs = integral_plasma Q_RF dV
      = 2*pi * integral_plasma r * Q_RF dr dz  [W]
```

Only `sigma_R` enters the dissipative term explicitly. `sigma_I` is reactive and may change the field solution, but it does not directly contribute to `Q_RF`.

## Exact evidence

```text
science head: fb27e232924a0ee11010669eff287d9b953f1a31
Actions run: 37836361274
artifact: Issue_202_Maxwell_M2_validation
artifact id: 11575123517
artifact sha256: 5eae092f1cc6fd224aadb26d53700deafeb02ec7add38103b8b715eee9eb5692
```

The MOOSE implementation uses only standard objects:

```text
ParsedMaterial(property_name=q_rf)
ElementIntegralMaterialProperty(mat_prop=q_rf, block=plasma)
```

The independent reference uses the same `qvt.msh`, assembles the complex scalar-RZ FEM system independently with SciPy, and integrates `r*|E|^2` with a degree-3 exact triangle rule.

## Baseline cross-solver power

Prescribed validation plasma:

```text
sigma = 5 - 10 i S/m
I_peak = 10 A
frequency = 13.56 MHz
```

Results:

```text
MOOSE P_abs        = 175.81487393245 W
independent P_abs  = 175.81488589464578 W
relative error     = 6.80385833654e-08
reference residual = 6.09517144120e-15
```

This is well inside the predeclared `0.5%` cross-solver power tolerance.

## Counterfactuals

### Lossless plasma

```text
sigma_R = 0
sigma_I = 0
source_scale = 1
MOOSE E_imag_l2 = 48.034985393912
MOOSE P_abs = 0 W
reference P_abs = 0 W
```

### Reactive-only plasma

```text
sigma_R = 0
sigma_I = -10 S/m
source_scale = 1
MOOSE field L2 = 35.366197855172
MOOSE P_abs = 0 W
reference P_abs = 0 W
```

The RF field remains nonzero while dissipative power is exactly zero. This discriminates reactive conductivity from collisional absorption.

### RF field off

```text
sigma_R = 5 S/m
sigma_I = -10 S/m
source_scale = 0
MOOSE field L2 = 0
MOOSE P_abs = 0 W
reference max |E| = 0
reference P_abs = 0 W
```

## Gate result

```text
RF_ABSORBED_POWER_FORMULA = PASS
SIGMA_R_ZERO_COUNTERFACTUAL = PASS
SIGMA_I_ONLY_COUNTERFACTUAL = PASS
E_RF_ZERO_COUNTERFACTUAL = PASS
MOOSE_REFERENCE_POWER_EQUIVALENCE = PASS
```

This is a bounded standalone Maxwell/RF-power validation. It does not establish the final oxygen-plasma conductivity closure, conservative FE-to-FV transfer, electron-energy coupling, copper skin/proximity physics, circuit drive, or full ICP scientific acceptance.

The next gate is M3: conservative transfer of `Q_RF` from the Maxwell FE field to the plasma electron-energy discretization, with volume-integrated power conservation across the transfer.
