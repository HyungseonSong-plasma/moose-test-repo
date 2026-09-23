# Issue #331 — monolithic charged drift-diffusion + ordinary Poisson

This lane is independent from Issue #310 modified/nonlinear-Poisson Gummel work.

## Evidence baseline

- Repository baseline: `ea3e63ba4e4edd75e8227748e185ddd5fbb106d8` (`main` at Stage-B start).
- Accepted heavy-transport evidence: Issue #306 Sequence08, accepted branch head `1b28a1bccbec4ccad5e597500142a7e7e06ef4a3`.
- Historical structural evidence only: `archive/Issue29_monolithic_performance_bound/monolithic_q0_reference.i`.

The Issue29 input is not a scientific baseline: it lacks the currently accepted electron-energy/wall/time semantics. It only demonstrates that charged variables and ordinary Poisson can coexist in one FV nonlinear problem.

## H_MONO_DD

Remove the outer electron/ion/Poisson Gummel iteration by making the following variables nonlinear unknowns of one MOOSE problem:

- `log_e` — electron molar-density logarithm;
- `n_epsilon` — normalized electron-energy density;
- `w_O2p`, `w_Om`, `w_Op` — accepted charged-heavy mass-fraction representation;
- `potential_plasma` — electrostatic potential.

Neutral gas state is frozen for the first discriminator. The charged subsystem is solved by one Newton solve at the electron physical timestep. No Boltzmann electron closure is introduced.

## Stage-A ownership census

### CHARGED_DD_POISSON

| unknown | representation | required residual terms |
|---|---|---|
| `log_e` | `c_e = exp(log_e)` mol/m3 | log-molar time derivative, electron diffusion, signed electrostatic drift, accepted electron wall particle flux |
| `n_epsilon` | normalized electron energy density | time derivative, energy diffusion, electrostatic drift, Joule heating, O2 elastic loss, accepted electron energy wall flux |
| `w_O2p` | heavy mass fraction | conservative `rho*w` time derivative, neutral-gas advection, mixture diffusion, + electrostatic migration, mass-frame electromigration correction, accepted wall loss |
| `w_Om` | heavy mass fraction | same, with negative migration sign |
| `w_Op` | heavy mass fraction | same, with positive migration sign |
| `potential_plasma` | V | ordinary Poisson diffusion + charge source from `log_e,w_O2p,w_Om,w_Op` |

### NEUTRAL_FLOW

`u`, pressure/density state, `w_O2s`, constrained `w_O2`, `w_O`, `w_Os`, gas temperature and neutral transport state remain outside the first charged prototype. Their same-time accepted state is frozen/read-only input to charged transport coefficients, neutral convection and chemistry. Stage E will restore their physical-time evolution.

## Non-negotiable charged-heavy flux

Calling this architecture "drift-diffusion" does **not** authorize dropping the neutral carrier velocity. The accepted charged-heavy flux is conceptually

```
Gamma_k = rho*w_k*u_g
        + Gamma_mixdiff,k
        + Gamma_E,k
        + Gamma_mass_frame,k
```

plus the accepted wall flux and source/time terms. Stage B must preserve these terms. Pure `drift + diffusion` is a different physics model and is not a valid performance discriminator.

## Ordinary Poisson contract

The physical equation remains unchanged:

```
-div(epsilon_r grad(phi)) = poisson_charge_source(log_e,w_O2p,w_Om,w_Op)
```

The current frozen-charge Poisson child is not copied literally because its charge variables are AuxVariables. In Stage B the charge material must consume the **nonlinear charged variables directly** so AD can propagate derivatives into the Poisson row.

## Genuine-monolithic Jacobian contract

Before performance comparison, the prototype must establish both directions of coupling:

```
d R_loge / d phi != 0
d R_energy / d phi != 0
d R_O2p / d phi != 0
d R_Om  / d phi != 0
d R_Op  / d phi != 0

d R_phi / d log_e != 0
d R_phi / d w_O2p != 0
d R_phi / d w_Om  != 0
d R_phi / d w_Op  != 0
```

The accepted electron drift/energy/Joule kernels already take potential as a functor and the accepted charged-heavy migration path is AD-based. The main Stage-C risk is the Poisson charge material: it must preserve AD dependence on all charged solver variables. If it strips derivatives, the system is only nominally monolithic.

## Stage-B minimum prototype

The first executable discriminator shall:

1. use the accepted 1D mesh (`0..0.01 m`, 20 cells);
2. preserve `log_e` and `n_epsilon` equations from the accepted electron child;
3. promote `w_O2p`, `w_Om`, `w_Op` from transferred/frozen fields to nonlinear variables in the same problem;
4. promote `potential_plasma` from the Poisson child into that same problem;
5. replace `potential_from_poisson` in electron/energy kernels with `potential_plasma`;
6. remove the Poisson `FullSolveMultiApp`, charge transfers and fixed-point controls entirely;
7. preserve the Sequence08 sheath-suppressed electron wall closure and accepted thermal charged-heavy wall model;
8. freeze neutral flow/composition at the exact same baseline state for the first short run;
9. use one implicit-Euler/Newton solve with automatic scaling and off-diagonal scaling enabled;
10. record nonlinear iterations, linear iterations if exposed, elapsed time, positivity, charge, `n_e`, mean energy and `phi` profiles.

## First discriminator clock

Start with a bounded short run before canonical qualification. Use the same electron physical timestep as the qualified reference and a horizon long enough to include multiple electron steps but short enough to diagnose Newton/Jacobian failures. Do not change tolerances to make the monolithic case appear successful.

After the short run is numerically sound, compare on the canonical `chi_e=100`, `chi_h=400`, ratio-4 clock and then the long horizon.

## Classification

- **Architecture feasibility:** SUPPORTED by current AD kernel structure and historical monolithic evidence.
- **Genuine monolithic Jacobian:** UNRESOLVED until Stage C proves the Poisson-row off-diagonal derivatives.
- **Performance hypothesis:** UNRESOLVED until an executable Stage-D A/B comparison measures total Newton + linear work and wall time.
