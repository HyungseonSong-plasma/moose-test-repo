# Issue #402 — EI/H rate owners and shared ideal-gas Functors

Status: DRAFT / P0–P2 verification only; **SCIENCE_HOLD** (no P3 scientific-parity claim).

## Factory ownership

- `EIRateCoefMaterial`: one electron-impact strict mean-energy lookup table and `n_e/N_A * c_target`, publishes the requested reaction progress.
- `HRateCoefMaterial`: JSON Chemistry `constant` or `power_law` volume progress from `T`, `rho_g`, and heavy-species mass fractions `Y_i`.
- `SurfaceReactionMaterial`: separate surface-only neutral thermal-sticking flux; no volume projection.
- Previous `RateCoeffMaterial` and `HeavyReactionRateMaterial` headers, sources and MOOSE registrations are deleted; no compatibility alias is registered.

## One root owner; no GasStateMaterial

```ini
[Physics]
  [Plasmas]
    files = oxygen_chemistry.json
    pressure = 1.333223684   # Pa = 10 mTorr
    temperature = 300        # K
    state_model = ideal_gas
  []
[]
```

`[Plasmas]` generates existing `ADParsedFunctorMaterial` providers for `p`, `T`, `rho_g`, `n_g`, `M_mix`. No `[GasState]` block, separate `GasStateMaterial`, or new MOOSE factory registration is needed. Without both root values, old external state Functors remain untouched (backward-compatible opt-in). When root values are set, JSON DD/Navier–Stokes transport actions use the root `p` and `T` outputs.

Initial volume and inlet compositions are declared on each heavy species in the Chemistry JSON, not in a top-level `gas_state` list:

```json
"species": {
  "O2": {
    "elements": {"O": 2}, "charge_number": 0,
    "molar_mass_kg_mol": 0.032,
    "initial_vol_mass_fraction": 0.9,
    "initial_inlet_mass_fraction": 1.0
  },
  "O": {
    "elements": {"O": 1}, "charge_number": 0,
    "molar_mass_kg_mol": 0.016,
    "initial_vol_mass_fraction": 0.1,
    "initial_inlet_mass_fraction": 0.0
  }
}
```

The root Action requires BOTH initial values and a positive molar mass for every
heavy species whenever the ideal-gas state is enabled. The volume and inlet
fractions each independently sum to one. A duplicate species record across
different JSON mechanism files must not contradict its initial or inlet data.

Generated `Y_<species>_initial_vol`, `Y_<species>_inlet`, and separate `rho_g_initial`/`rho_g_inlet` and `M_mix_initial`/`M_mix_inlet` are constant
Functor input DATA. They are **not** implicit solver initial/boundary operators:
only active solver and boundary configurations know which variables and inlet
boundaries exist. If no Navier–Stokes live composition is configured, the root
Action also generates fixed `Y_<species>` from initial volume values. With
Navier–Stokes transport active, `rho_g` uses live mass-fraction Functors
already configured in `transport_coefficients.navier_stokes` (and verifies the
complete heavy-species set). This conditional distinction prevents a stored
initial fraction from silently replacing an evolving composition.

```text
Y_i = rho_i / rho_mix                    # dimensionless mass fraction, sum(Y_i) = 1
M_mix = 1 / sum(Y_i / M_i)               # kg/mol
rho_g = p / (R * T * sum(Y_i / M_i))     # kg/m^3
n_g = p / (k_B * T)                      # particles/m^3
```

`Y_i` values are solver Functors, not fixed constants in JSON. The parsed expression is AD-differentiable and reflects composition changes. The root parser enforces both stored INITIAL composition sums; the generic parsed material does not enforce runtime `sum(Y_i)=1` for evolving fields; the state owner must maintain physically valid nonnegative, normalized mass fractions. This is not a new species-state solver.

Example: pure O2 at 10 mTorr and 300 K gives approximately `rho_g = 1.7105e-5 kg/m^3`, not the earlier synthetic `3.2e-5` test fixture.

## Scope and gates

- P0: renamed factory and consumer contracts, analytic ideal-gas mixture oracle, existing Stage-5 static/analytic contracts.
- Native P1: compile in pinned MOOSE OCI.
- Native P2: H01–H05 check-input, synthetic sticking input with root ideal-gas Functors, EI direct-material smoke check-input.
- P3 numerical scientific parity, charged wall semantics, global molar-mass reconciliation with the transport TXT tables, and runtime `Y_i` normalization are not established. Do not merge as a science-accepted change.

Parent PR: #525. This follow-up PR: #526.

### Root-state option migration (2026-11-13)

`[Physics]/[Plasmas]` uses `state_model = ideal_gas` (not `model`). Every solved heavy `mass_fraction_variable` receives its JSON `initial_vol_mass_fraction` as an FVConstantIC, without an enable switch. An explicitly positive `sccm` plus named `inlet_boundaries` activates the JSON fraction FVDirichletBC on solved species; omitting `sccm` omits that inlet BC, but not the IC. The SCCM *number* currently does not determine a flow flux/velocity and must not be interpreted as a full feed-flow implementation. See the dedicated live-species IC/inlet ownership document for the separate DriftDiffusion Continuity/Energy BC survey.
