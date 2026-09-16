# Issue 243 T1 — coupled log-molar electron particle conversion

T1 starts from the accepted Issue-217 coupled sheath/SEE/Poisson/chemistry composition and changes only the electron **particle** representation.

## Representation

- solved variable: `log_e = ln(c_e / (1 mol/m^3))`
- conservative concentration: `c_e = exp(log_e)` mol/m^3
- physical number density: `n_e_physical = N_A * exp(log_e)` 1/m^3
- no `n_ref` is permitted in the particle time, diffusion, drift, volumetric source, primary-sheath particle flux, or SEE particle flux.

Electron energy remains the existing `n_epsilon` representation in T1. Where that legacy energy owner still requires normalized density, T1 may construct an explicitly energy-only compatibility functor; it is forbidden from the particle residual and Poisson/chemistry physical-density path.

T1 does not alter reaction progress, heavy species, Poisson physics, sheath suppression, SEE coefficients, or electron-energy solved representation. Stage T2 owns the energy conversion.
