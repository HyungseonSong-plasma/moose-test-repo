# Issue #402 — live Y_i(t,x), JSON initial IC, and inlet BC handoff

Status: DRAFT, source-bound P0/P1/P2. SCIENCE_HOLD (no physical P3 parity).

## Input contract

Define the physical species once in `[Plasmas]/files` Chemistry JSON:

```json
"species": {
  "O2": {
    "elements": {"O": 2}, "charge_number": 0,
    "molar_mass_kg_mol": 0.032,
    "initial_vol_mass_fraction": 0.9,
    "initial_inlet_mass_fraction": 1.0,
    "mass_fraction_variable": "w_O2"
  },
  "O": {
    "elements": {"O": 1}, "charge_number": 0,
    "molar_mass_kg_mol": 0.016,
    "initial_vol_mass_fraction": 0.1,
    "initial_inlet_mass_fraction": 0.0,
    "mass_fraction_variable": "w_O"
  }
}
```

Every heavy species in a root `ideal_gas` mechanism must specify exactly
ONE **current-state owner**: either `mass_fraction_variable` (solved FV species)
or `mass_fraction_functor` (derived constrained species, e.g.
`w_O2_constraint = 1 - sum(w_others)`). These are validated nonempty
identifier-like names. The owner MUST be supplied by the solver input or an
existing derived Functor; no constant `Y_i` is auto-generated from JSON initial
metadata. Old root behaviour was physically unsafe for evolving mixtures.

The root Action generates canonical `Y_<species>` aliases bound to those
real-time variables or derived Functors. It NEVER uses
`initial_vol_mass_fraction` as a surrogate for live `Y_i(t,x)`.
All four consumer classes already evaluate their bound AD Functors at the
requested `(r,state)`, so naming and wiring is sufficient:

- `NVTransportMaterial`: root-generated NV Physics chooses canonical
  `Y_<species>` for mixture transport and thermal diffusion
- `HRateCoefMaterial`: `density=rho_g`, `temperature=T`,
  `mass_fractions='Y_...'` for each reactant
- `SurfaceReactionMaterial`: same live concentration composition at
  walls; **not** `Y_<species>_inlet`
- `PhysicsPlasmaChargeDensityMaterial`: `ion_mass_fractions='Y_Op ...'`;
  actual ion density/charge uses the same dynamic `rho_g`

The root `rho_g`, `M_mix` evaluations now depend on solver-state
`Y_i(t,x)` even if no NV transport action is active. Distinct
`rho_g_initial` and `rho_g_inlet` are metadata-only static EOS
calculations for initial and inlet data, not replacements for `rho_g`.

## Optional IC and explicit Dirichlet inlet ownership

```ini
[Physics]
  [Plasmas]
    files = oxygen_chemistry.json
    pressure = 1.333223684
    temperature = 300
    model = ideal_gas
    initialize_species_mass_fractions = true
    inlet_boundaries = left
    inlet_bc_model = dirichlet
  []
[]
```

The root Action creates one `FVConstantIC` on each
`mass_fraction_variable` with value `initial_vol_mass_fraction`.
With `inlet_bc_model=dirichlet`, it creates one `FVDirichletBC` per solved
species on the explicitly named `inlet_boundaries`, taking
`initial_inlet_mass_fraction` as the boundary value. It does not
generate IC/BC for a `mass_fraction_functor`: a constrained species must
remain dependent on solved species in both domains.

IC generation is an explicit **opt-in** so old solver variables and existing
user-supplied ICs are not silently overridden. If enabled, remove any
other ICs (including inline initial conditions) on those exact variables.
Boundary creation is opt-in and fail closed without a named inlet sideset.
Do not add a second BC to any variable/sideset pair.

**SCCM and flow-driven mass-flux inlet contracts are DIFFERENT.** Existing
WCNSFVMassFluxBC/WCNSFVScalarFluxBC models use postprocessors
`inlet_mdot` and `inlet_mdot_<id>`, not Dirichlet concentrations. They
MUST retain their existing flux owners; their input builder must calculate
`inlet_mdot_<id> = inlet_mdot * initial_inlet_mass_fraction_<id>`.
Do not automatically stack `FVDirichletBC` over a WCNSFVMassFluxBC.
This PR does not silently rewrite archived or production SCCM cases.

## Native P2 demonstration

`physics_app/ci/json_species_live_all4_p2.json` and `.i` provide:

- `w_O2`, `w_O`, `w_Op` as FV solved state
- root-generated volume ICs, inlet Dirichlet BCs and canonical live Y aliases
- H91 synthetic volume and H90 synthetic surface reaction rate providers
- NV oxygen transport and plasma charge density consuming the identical
  dynamic mass fractions
- no claim that synthetic reaction H91 or boundary condition represents a
  physical oxygen discharge or validated reactor inlet

A separate P2 mutation case declares O2 as
`mass_fraction_functor=w_O2_constraint` (read-only), and verifies that
the solver/BC creation skips it while the other solved species still
receive IC/BC.

## Verification and limits

P0: `tests/test_issue402_species_live_ic_inlet.py`, plus prior Chemistry
JSON and rate/transport source contracts.

P1: pinned-MOOSE native Physics application compilation.

P2: H01-H05 and thermal-sticking checks; all-four live-Y input; positive
derived-species mode; fail-closed invalid/missing/duplicated live-owner tests.

Not verified: P3 transient solution, physical inlet flux conservation,
source-to-source reactor parity, transport TXT/JSON molar mass scientific
reconciliation. Explicit direct user-authored density, reaction, charge and
SCCM composition bindings need their own scenario checks before release.
