# Issue #402: species-owned initial volume / inlet composition consumer survey

Status: **DRAFT / SCIENCE_HOLD**. Source-bound static P0 and Native P1/P2 gates are
separate from scientific P3 validation. Parent PR #526; implementation PR #527.

## Schema and scope

Canonical Chemistry JSON `species.<id>` owns `charge_number`,
`molar_mass_kg_mol`, `initial_vol_mass_fraction`, and
`initial_inlet_mass_fraction`. No `gas_state` object. Both initial fractions
are optional on legacy non-gas mechanisms but BOTH required for every heavy
species when `[Plasmas] pressure/temperature/model=ideal_gas` is enabled.
Fractions must be finite within [0,1]. The independent volume and inlet totals
each equal one (absolute tolerance 1e-8), including explicitly zero species.
Electrons cannot have heavy mass fractions. Conflicting duplicate species
initial/inlet values across files are rejected.

For initial pure-O2 feed but mixed starting plasma, for example:
`O2: vol 0.9, inlet 1.0`; `O: vol 0.1, inlet 0.0`. They are **not** the same
state, and the inlet data must never be substituted for initial volume data.

## Active consumer inventory / authoritative handoff

| Path | Information consumed | Current ownership and use | Work remaining or boundary |
| --- | --- | --- | --- |
| `physics_app/src/physics/plasma/Chemistry.C` / `Chemistry.h` | All species attributes / merged JSON | Parse, validate, merge, normalize initial volume and inlet, publish `Y_<id>_initial_vol` and `Y_<id>_inlet` | Implemented |
| `physics_app/src/physics/plasma/PlasmaInterface.C` | Root `[Plasmas]` ownership | Shares one JSON mechanism among Physics | Implemented |
| `physics_app/src/physics/plasma/NVTransport.C` and `NVTransportMaterial.C` | `p`, `T`, **live** mass fractions and molar masses | Mixture transport and thermal diffusion; root EOS reads NV live mass-fraction Functors when NV is configured | **Molar masses are still separately read from transport TXT**; add consistency gate before science acceptance |
| `physics_app/src/physics/plasma/DDContinuityEq.C` / `DDTransportMaterial.C` | `p`, `T` for reduced coefficients; species name and initial **number** density | Uses common root gas Functors, but existing `fem_species`/`fvm_species` pair syntax initializes charged number-density state | Number density is not mass fraction; do not silently remap |
| `physics_app/src/materials/HRateCoefMaterial.C` | `rho_g`, `T`, **live** `Y_i`, species molar mass | H-volume progress `R_Hnn`; configured `.i` Functors remain explicit | Chemistry initialization does not independently create reaction Material |
| `physics_app/src/materials/SurfaceReactionMaterial.C` | `rho_g`, `T`, neutral `Y_i` | Surface sticking and signed wall mass flux, distinct from inlet composition | `Y_<species>_inlet` does NOT prescribe wall sticking |
| `physics_app/src/materials/PhysicsPlasmaChargeDensityMaterial.C` | Mixture density and ion mass fractions | Ion number density/space charge | Existing standalone Material still needs `density = rho_g` binding; not auto-generated |
| `physics_app/src/functormaterials/PhysicsIonWallFluxMaterial.C` | Gas/ion temperature and ion number density | Wall flux, not inlet feed | Uses gas temperature only where ion temperature mode selects it |
| `physics_app/src/fvkernels/PhysicsFVMassFractionAdvection.C`, `PhysicsFVMassFractionTimeDerivative.C`, `PhysicsFVConservativeMassFractionTimeDerivative.C` | Solved heavy mass-fraction variables | The actual evolving state `Y_i(t,x)` must replace static initial values in an active transport model | Existing FV owners; do not silently inject a second IC/residual |
| `experiments/Issue15_charged_heavy_migration`, `Issue21_qvt_six_species_bulk_advection`, `Issue22_qvt_transient_species_accumulation` | Initial and inlet mass fractions, SCCM flux, boundary mass rates | Existing experiments retain independent validated inlet and volume settings | Scenario-specific migration requires source evidence and boundary mapping; no hidden rewrite of published cases |
| `experiments/historical_recipe_support/issue31_r4_qf1.py` | Distinct pure-O2 inlet vs ionized initial plasma | Existing staged builder explicitly preserves this separation | Preserve when migrating to JSON metadata |
| `experiments/historical_recipe_support/issue192_s5r.py`, Stage-5 CI | `Y_i`, density, rates | Active H-rate input generator uses explicitly bound mass fraction Functors | Compatible with new opt-in root EOS; not automatically converted |
| `physics_app/ci/json_surface_rate_p2.json`, `.i` | Both initial fraction keys | P2 fixture uses 0.9/0.1 volume, 1.0/0.0 inlet; `Y_O2` static derived from JSON | Synthetic thermal sticking only, **no scientific wall parity** |

## Data flow / no duplicate ownership

```text
Chemistry JSON species:
  charge_number, molar_mass_kg_mol
  initial_vol_mass_fraction  ------> Y_<id>_initial_vol [initial IC data]
  initial_inlet_mass_fraction -----> Y_<id>_inlet       [boundary/feed data]
                                              |
[Plasmas] pressure, temperature, ideal_gas ----+--> p [Pa], T [K], n_g
                                                  |
NO Navier–Stokes live mixture: Y_<id> = initial_vol_mass_fraction (FIXED ONLY)
YES Navier–Stokes live mixture: Y_i(t,x) from NV mass_fractions Functor names
                                                  |
                                                  +--> M_mix, rho_g
                                                         |
                                              H-rate / Surface / Charge consumers
```

Formula: `M_mix = 1/sum(Y_i/M_i)`,
`rho_g = p*M_mix/(R*T)`, `n_g = p/(k_B*T)`.

## Explicitly NOT automated

1. **Initial state ICs**: JSON contains default initial values, but does not
   guess whether solver variables are `w_O2`, `w_O2_constraint`, or another
   implementation. IC owner still maps each field to the correct solved variable.
2. **Inlet BCs**: JSON contains feed fractions, but has no inlet boundary name,
   flux direction, or SCCM mass-flow policy. The BC owner must bind
   `Y_<id>_inlet` to its actual inlet flux/Dirichlet operator; wall sticking
   and inlet mass flow have different semantics.
3. **Live normalization**: Stored initial compositions are sum-checked; evolving
   `Y_i(t,x)` are not normalized by their initial values. Solver owns
   positivity and mixture continuity.
4. **Transport molar masses**: Collision TXT and Chemistry JSON both store
   molar mass. Native compilation or `--check-input` alone cannot establish
   scientific equality. Add direct-value validation before P3.
5. **Historical archives**: Published/science-frozen `.i` and evidence files
   are not mass-modified. Case-by-case migrations are required.

## Reproducible exhaustive path audit

`python3 physics_app/ci/audit_issue402_initial_composition_routes.py \
--json-output <path> --markdown-output <path> --fail-on-legacy`

This scanner walks **every supported active-source text file** under
`physics_app`, `experiments`, `physics_harness`, `tests`, and `ci`,
including C++, Python, `.i`, JSON and workflows. It reports path, exact
matching line numbers, route category and all JSON initial records; it rejects
any retained top-level `gas_state` JSON. It deliberately excludes historical
`archive/` and prose documentation from the active implementation scan.
The pinned CI publishes both JSON and Markdown reports as artifacts.

P0 contract and analytical checks:
`tests/test_issue402_species_initial_composition.py`.
Native positive and fail-closed P2:
`physics_app/ci/check_issue402_species_initial_composition_p2.py`.

## Decision and gating

Separate species initial and inlet mass-fraction ownership is approved by the
request. Automatically generating solver ICs, inlet BCs, and rewriting
published scientific scenarios are NOT authorized by these metadata changes.
Maintain `SCIENCE_HOLD` until physical integration and P3 parity are shown.
