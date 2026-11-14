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
    model = ideal_gas
  []
[]
```

`[Plasmas]` generates existing `ADParsedFunctorMaterial` providers for `p`, `T`, `rho_g`, `n_g`, `M_mix`. No `[GasState]` block, separate `GasStateMaterial`, or new MOOSE factory registration is needed. Without both root values, old external state Functors remain untouched (backward-compatible opt-in). When root values are set, JSON DD/Navier–Stokes transport actions use the root `p` and `T` outputs.

For `rho_g`, the mechanism must identify the complete heavy-mixture mass-fraction Functors. Define once in the Chemistry JSON:

```json
"gas_state": {
  "species": ["O2", "O"],
  "mass_fractions": ["Y_O2", "Y_O"]
}
```

The JSON `species` entries must include matching positive `molar_mass_kg_mol`. A configured Navier–Stokes species/mass_fractions pair is an alternative source of the composition binding. Unknown, electron, or massless species are rejected. Conflicting gas_state declarations across files are rejected.

```text
Y_i = rho_i / rho_mix                    # dimensionless mass fraction, sum(Y_i) = 1
M_mix = 1 / sum(Y_i / M_i)               # kg/mol
rho_g = p / (R * T * sum(Y_i / M_i))     # kg/m^3
n_g = p / (k_B * T)                      # particles/m^3
```

`Y_i` values are solver Functors, not fixed constants in JSON. The parsed expression is AD-differentiable and reflects composition changes. The generic parsed material does not itself enforce runtime `sum(Y_i)=1`; the state owner must maintain physically valid nonnegative, normalized mass fractions. This is not a new species-state solver.

Example: pure O2 at 10 mTorr and 300 K gives approximately `rho_g = 1.7105e-5 kg/m^3`, not the earlier synthetic `3.2e-5` test fixture.

## Scope and gates

- P0: renamed factory and consumer contracts, analytic ideal-gas mixture oracle, existing Stage-5 static/analytic contracts.
- Native P1: compile in pinned MOOSE OCI.
- Native P2: H01–H05 check-input, synthetic sticking input with root ideal-gas Functors, EI direct-material smoke check-input.
- P3 numerical scientific parity, charged wall semantics, global molar-mass reconciliation with the transport TXT tables, and runtime `Y_i` normalization are not established. Do not merge as a science-accepted change.

Parent PR: #525. This follow-up PR: #526.
