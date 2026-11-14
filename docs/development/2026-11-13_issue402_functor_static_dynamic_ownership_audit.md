# Issue #402 — static vs live Functor ownership and optimization candidates

**Status:** source survey / architectural recommendation only, stacked Draft PR #530.
**Authority:** current branch `issue-402-sccm-inlet-flow-native`, not
historical one-shot artifacts. No runtime timing, numerical equivalence or P3
science acceptance. **SCIENCE_HOLD**.

## Rule: classify the dependency graph, not the class name

A quantity is **setup-only** iff *every* dependency is frozen by the active
scenario contract: fixed JSON, root input options, and explicitly supplied
geometry. A MOOSE `Functor` API by itself does not mean the value is
time-dependent, but a live solved variable must never be replaced by a
setup snapshot. Converting to a `Postprocessor` is not a safe drop-in when
a consumer explicitly requires `MooseFunctorName` or differentiable
`ADReal`. Preserve API/AD semantics separately from evaluation cost.

| Provider and current outputs | Dependency | Classification | Action |
| --- | --- | --- | --- |
| `SCCMInletFlow`: `plasma_inlet_mdot`, area, speed, flux, per-species feed | fixed SCCM, inlet JSON Y, mass, p/T, area and standard molar volume | **setup-only** | **Implemented:** pure C++ mapping at construction; publish immutable ConstantPostprocessors |
| Root `PlasmasAction` `p`, `T`, `n_g` | current contract fixed user p and T | setup-only in current root model | **IMPLEMENTED (P1/P2 pending):** setup-computed numeric values supplied through `ADGenericFunctorMaterial`; stable `p`/`T`/`n_g` Functor names and AD interface. |
| Root `Y_<id>_initial_vol`, `Y_<id>_inlet`, `M_mix_initial`, `M_mix_inlet`, `rho_g_initial`, `rho_g_inlet` | fixed JSON initial/feed fractions plus p/T | setup-only | **IMPLEMENTED (P1/P2 pending):** `IdealGasMixtureState::evaluate` owns static state once; `ADGenericFunctorMaterial` retains the old Functor API. SCCM inlet reuses the same fixed EOS calculation. |
| Root `Y_<id>` aliases, `M_mix`, `rho_g` | live `mass_fraction_variable` or `mass_fraction_functor` | **live** | Keep AD Functor and solver derivatives; any replacement by setup constants breaks evolving composition and EOS. |
| `DDTransportMaterial` in `constant` mode | model constants only | setup-only *coefficients* | **Candidate B:** precompute/retain constant coefficients internally, but preserve the current AD Functor names/properties required by drift-diffusion. Measure before changing. |
| `DDTransportMaterial` in `lookup`/`functor` mode | solved mean energy, density, p/T or upstream transport Functors | live | Keep state-aware interpolation/AD. A constant-table *load* already belongs in construction; lookup *evaluation* does not. |
| `NVTransportMaterial` `D_T`, `kT`, `D_mix` | live composition, p/T, Te, ne; charged and mixture closure | **live, potentially expensive** | **Candidate C (profile first):** repeated `evaluate(...)` calls across coefficient output Functors suggest shared per-state evaluation/caching opportunity. Never cache by time alone; element/face, state, AD derivative and nonlinear-iteration identity matter. |
| `EIRateCoefMaterial`, `HRateCoefMaterial`, `SurfaceReactionMaterial` | electron energy, densities, temperature and live concentrations | live | Keep AD and on-demand kinetics. Static reaction constants/tables can remain pre-parsed; not progress rates. |
| `PhysicsPlasmaChargeDensityMaterial`, `PhysicsElectronMeanEnergyMaterial` | live electron/ion density, electron energy and gas state | live | Keep AD and current state; do not freeze source terms or Poisson coupling. |
| `PhysicsElectronAdjacentSheathWallFluxMaterial`, `PhysicsElectronWallFluxMaterial`, `PhysicsIonWallFluxMaterial` | sided face, electric-potential gradient, electron/ion state and density | live, face-sensitive | Keep sided FaceArg/electric field/AD dependencies; precompute only truly geometric constants if independently proved and profiled. |

## Priority and hard gates

1. **This PR:** extract SCCM formula into pure C++ with stable names and
   fixed-case calculation; keep root generated Postprocessor interface. Unit
   test the actual C++ translation unit independently of MOOSE, plus historical
   Issue #19/#21 analytic and wrong-reference/area/species mutations.
2. **This PR:** Candidate A fixed `p`, `T`, static initial/inlet mixture,
   `n_g` now use numeric `ADGenericFunctorMaterial` aliases, with untouched
   names, units and zero AD derivative. Native P1/P2 must prove provider
   compatibility and volume-vs-inlet distinction before acceptance.
3. **Later, contingent on profiling:** Candidate C `NVTransportMaterial`
   repeated evaluation is more likely to dominate cost than one-time SCCM.
   Prove recomputation from actual source/solver profiling before introducing
   a cache; require state/face/nonlinear-iteration sensitivity and numerical
   parity, including sensitivity to changed live Y, Te and ne.
4. **No action:** energy/charge/wall/kinetic live Functors must not become
   precomputed setup values. Faster but physically stale output is invalid.

## Acceptance limits

P0 independent C++ unit and source ownership: required; P1 native application
build: pending; P2 real `physics-opt --check-input`: pending; P3 physical
inlet flow, coupled charge/transport/wall numerical parity: not run.
All optimization candidates beyond the one-time SCCM extraction are **review
findings**, not unapproved source migrations.
