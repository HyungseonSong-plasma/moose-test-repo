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

## Mandatory heavy-species FV IC; SCCM-enabled Dirichlet inlet ownership

```ini
[Physics]
  [Plasmas]
    files = oxygen_chemistry.json
    pressure = 1.333223684
    temperature = 300
    state_model = ideal_gas
    inlet_boundaries = inlet
    sccm = 100
    inlet_area = 0.05
    standard_molar_volume = 0.0224136
  []
[]
```

The root Action **always** creates one `FVConstantIC` on every
species-owned **solved** `mass_fraction_variable`, using JSON
`initial_vol_mass_fraction`. There is no
`initialize_species_mass_fractions` switch. A derived `mass_fraction_functor`
is read-only; its value comes from the independent solved states and it
must not receive a second IC.

An explicitly supplied **positive and finite** `sccm` causes the
root Action to create one `FVDirichletBC` for each solved species on
the named `inlet_boundaries`; the boundary value is the JSON
`initial_inlet_mass_fraction`. No `sccm` means **no generated inlet BC**,
but still creates all solved species ICs. `inlet_boundaries` without `sccm`
is rejected; `sccm` without inlet sidesets is rejected.
The old root `model`, `inlet_bc_model`, and
`initialize_species_mass_fractions` options are retired, with no aliases.

SCCM is an inlet flow-rate specification (standard cm³/min), not only a
composition BC switch. The existing Issue #19 and Issue #21 input contracts
already use `${fparse}` and Receiver Postprocessors to convert standard
volumetric flow to mass flow. This root Action reuses **the same numerical
identity**, sourcing `M_inlet` and feed fractions from authoritative species
JSON instead of duplicating the hand-entered mixture expression in every .i.

```text
M_inlet  = 1 / sum_i(Y_i_inlet / M_i)             [kg/mol]
Q_std    = sccm * 1e-6 / 60                      [m^3/s]
mdot     = Q_std * M_inlet / standard_molar_volume [kg/s]
rho_in   = pressure * M_inlet / (R * temperature) [kg/m^3]
flux     = mdot / inlet_area                     [kg/m^2/s]
speed    = flux / rho_in                         [m/s]
mdot_i   = mdot * Y_i_inlet                      [kg/s]
```

`inlet_area` [m²] is required with `sccm` and is **provided externally**;
no AreaPostprocessor is created. `standard_molar_volume` [m³/mol]
defaults to the existing Issue #19 value 0.0224136 and must be changed if
the standard reference condition differs. Flow speed is a **magnitude**;
the existing WCNS BC owns its sign and inlet direction.

The root delegates conversion and the named-value mapping to the pure C++ `SCCMInletFlow::calculate()` module in `physics_app/src/physics/plasma/SCCMInletFlow.C`. The `PlasmasAction` registers returned values as `ConstantPostprocessor` objects without hosting the equations. Values are computed **once at input construction**, not reevaluated per quadrature point or timestep. The mathematical contract and output names are unchanged from the pre-extraction version.

The root creates `ConstantPostprocessor` providers:
`plasma_inlet_mdot`, `plasma_inlet_area`, `plasma_inlet_rho`,
`plasma_inlet_mass_flux`, `plasma_inlet_speed`,
`plasma_inlet_Y_<id>`, and `plasma_inlet_mdot_<id>`.
These provide the real MOOSE PostprocessorValue interface required by
existing `WCNSFVMassFluxBC` and `WCNSFVScalarFluxBC` consumers.
For a mixture mass-flow inlet, explicitly bind
`mdot_pp = plasma_inlet_mdot`, `area_pp = plasma_inlet_area` on the
existing WCNS mass and momentum inlet BCs. Scalar flux BC consumers must
use the matching species fraction/feed values and retain their existing
owner semantics.

`inlet_species_bc_ownership = root_dirichlet` (default) creates FVDirichletBC
for solved mass-fraction variables. `external_flux` suppresses all those
generated Dirichlet BCs; an explicit WCNS scalar-flux BC can then own
each variable/sideset without double application. The Action does not
automatically generate momentum, velocity, pressure or flux BC objects,
or infer inlet direction/sideset area. It does not rewrite historical S6
inputs or provide a P3 flow-conservation claim.

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

## DriftDiffusion BC owner survey (2026-11-13)

- `DDContinuityEq.C` registers `add_variables_physics`, `add_ics_physics`, `check_integrity`, `add_kernel`, `add_functor_material`. It does **not** register `add_bc`. It creates FEM/FV `log_<species>` variables and log-molar `ConstantIC`/`FVConstantIC` when positive number-density pairs are supplied. These are number-density states, not heavy `Y_i` mass fractions. Native/user BCs retain ownership.
- `DDEnergyEq.C` registers `add_variables_physics`, `add_ics_physics`, `check_integrity`, and `add_kernel` only. It supports FEM electron `log_e_energy` and generates `ConstantIC = log(initial_molar_energy_density_eV)` when auto-creating the variable. It does not register `add_bc`, and FV electron energy is currently unsupported by this Physics action.
- Electron/ion wall flux and dielectric BCs remain dedicated Native implementations. There is no sound basis for treating electron-energy wall conditions or electron log-density as heavy-species Dirichlet (Y_i) boundary values.
