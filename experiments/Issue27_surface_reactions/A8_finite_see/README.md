# Issue #27 A8 — finite ion-induced SEE + 4 eV energy ledger

A8 extends the accepted A7 COMSOL-style electron thermal wall model with finite ion-induced secondary electron emission from the two positive oxygen ions.

Frozen COMSOL oxygen-ICP coefficients:

```text
O2+ -> O2   gamma_SEE = 0.05   mean secondary-electron energy = 4 eV
O+  -> O    gamma_SEE = 0.05   mean secondary-electron energy = 4 eV
O-          gamma_SEE = 0
```

The SEE particle flux uses the accepted positive-ion wall incidence, including both thermal/sticking surface loss and one-sided electric migration:

```text
Gamma_e,SEE
  = 0.05 * (Gamma_O2+,wall + Gamma_O+,wall)
```

with

```text
Gamma_i,wall = Gamma_i,surface + Gamma_i,migration
```

The emitted electrons travel from the wall into the plasma, so in the outward-positive convention

```text
Gamma_e,SEE,out = -Gamma_e,SEE
```

and the normalized `n_hat = n_e/n_ref` FV boundary source therefore uses a positive `FVFunctorNeumannBC.factor = +1`.

The corresponding secondary-electron energy flux contract is

```text
P_SEE = Gamma_e,SEE * e * 4 eV-equivalent-volts
```

which has SI units W/m2 before surface integration and W after integration.

## Two-case discriminator

```text
see_off
  accepted A6 heavy wall chemistry ON
  accepted ion surface + migration wall flux ON
  accepted A7 electron thermal wall loss ON
  finite SEE OFF

see_on
  same physics
  + O2+/O+ SEE particle source with gamma = 0.05
  + 4 eV SEE energy-flux ledger
```

The short A7 one-step discriminator timestep (`1e-10 s`) is retained.

## Acceptance

Scientific evidence must establish:

- zero SEE particle and energy flux in `see_off`;
- `Gamma_e,SEE = 0.05*(Gamma_O2+ + Gamma_O+)` using the measured positive-ion wall incidence;
- emitted-electron inventory closure in the solved electron-density equation;
- expected charge response and Gauss consistency;
- nonnegative electron density and preserved heavy-species composition closure;
- energy ledger equal to 4 eV per emitted electron.

## Important scope boundary

A8 validates and couples the **SEE particle source** now. It also validates the complete **4 eV SEE energy-flux contract**, but R4-QF1 has no solved electron-energy variable. Therefore A8 does not pretend to evolve electron energy.

When #26 activates the electron-energy equation, it must connect this already-validated SEE energy flux to the electron-energy wall equation without changing `gamma = 0.05` or the `4 eV` mean energy.

Run:

```bash
python qpx -i all
python qpx -e experiments/Issue27_surface_reactions/A8_finite_see/experiment.json
```
