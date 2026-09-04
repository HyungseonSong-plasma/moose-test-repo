# Issue #27 A7 — COMSOL-style electron thermal wall loss

A7 replaces the accepted A6 matched electron charge-ledger control with the COMSOL ICP-style random thermal electron particle loss while preserving the accepted A6 heavy-wall chemistry and charged-heavy surface + one-sided migration transport.

For the normalized electron solver unknown

```text
n_hat = n_e_physical / n_ref
```

and electron reflection coefficient `r_e = 0`, the outward-positive wall particle flux is

```text
Gamma_e,out / n_ref
  = 0.5 * n_hat * v_e,th

v_e,th
  = sqrt(16 * e * mean_energy_eV / (3 * pi * m_e))
```

where the current R4-QF1 transport contract supplies `mean_energy_eV = 5.73276 eV` through `mean_en`. This is equivalent to COMSOL's Maxwellian thermal-speed form with `mean_energy = 3/2 k_B T_e`.

The MOOSE sign mapping remains

```text
physical outward-positive flux
  -> FVFunctorNeumannBC.factor = -1
```

A7 freezes:

```text
electron reflection       = 0
electron wall migration   = OFF
secondary emission (SEE)  = 0
```

The batch contains:

```text
control
  accepted R4-QF1/A6 wall objects present but all new wall fluxes disabled

electron_thermal_only
  heavy surface/migration wall fluxes disabled
  COMSOL thermal electron particle loss enabled

combined_thermal
  accepted A6 heavy surface chemistry enabled
  accepted A6 charged-heavy surface + electric migration enabled
  matched A6 electron ledger removed
  COMSOL thermal electron particle loss enabled
```

Acceptance evidence checks:

- electron inventory loss against the integrated state-dependent thermal wall flux;
- nonnegative electron density;
- independently predicted net plasma-volume charge change from heavy-wall current plus electron thermal loss;
- Gauss-law consistency;
- N-1 heavy-species composition closure.

A7 does **not** force heavy-wall and electron-wall currents to cancel. The resulting charge response is part of the scientific evidence.

The current R4-QF1 model has no electron-energy solver variable. Therefore the COMSOL electron-energy wall flux is deliberately not fabricated in A7; it remains coupled to the later electron-energy/#26 stage together with finite SEE.

Run:

```bash
python qpx -i all
python qpx -e experiments/Issue27_surface_reactions/A7_comsol_electron_wall/experiment.json
```
