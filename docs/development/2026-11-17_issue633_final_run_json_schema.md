# Issue #633 — S6 New-only single-file run JSON candidate

Status: **PROPOSED SCHEMA, NOT P2/SCIENCE ACCEPTED**. The active draft integration
PR #665 contains the candidates. Historical Hybrid S6 sources and runner remain unchanged.

## Exact files

- `experiments/Issue402_plasma_dsl_g1/chemistry/unified_s6_417_newonly.json`
- `experiments/Issue402_plasma_dsl_g1/chemistry/unified_s6_941_newonly.json`

Each file contains seven species, eight pinned reaction entries, **five grouped**
drift-diffusion boundaries. They instantiate 12 ion FV BC objects and 8
electron/energy FEM sheath BC objects without changing the historic
electron's inlet/outlet boundary treatment. The source has one electron
surface-current selector. There is **no synthetic progress rate** in
either file. Eight live `R_*` progress producers must be available in staged
new-only Scratch input before P2. Ion mobility/diffusivity are now self-owned
JSON constants; external ion coefficient Functor producers are not required.
Reactions are retained byte-semantically from the pinned unified Hybrid files.

## Uniform species base

Every species (`e`, `O2`, `O`, `O2p`, `Om`, `Op`, `O2a`) declares the
same base fields:

```json
{
  "elements": {"O": 2},
  "charge_number": 1,
  "molar_mass": 0.032,
  "temperature_eV": null,
  "sticking_coefficient": 1,
  "initial_number_density": 1000000000000001.6,
  "transport_coef": {
    "type": "constant",
    "file": "none",
    "unit": "physical",
    "mobility": 10,
    "diffusivity": 0.25851999786435537
  }
}
```

- `elements` is the **nuclear composition** used by
  `ChemistryData::validateReaction` to verify atomic conservation. `e`
  has `{}`, charge -1. It does not construct a MOOSE operator itself.
- `molar_mass` is kg/mol for every species, **including electrons**
  (`5.485799096195737e-7` kg/mol from electron mass × Avogadro constant).
  The archived ion Wall Material consumes this as its molar-mass parameter.
  The separate older `molar_mass_kg_mol` for a complete gas-mixture closure
  is unchanged in historical fixtures; a new mass value does **not**
  activate a second Navier–Stokes mixture closure.
- `temperature_eV` is the kinetic temperature scale `k_B T` in eV.
  `null` means **no independent species temperature IC is specified**.
  Ion Wall Materials retain their original 300 K gas-temperature fallback
  with `null`. A numeric ion temperature is a **prescribed wall thermal
  parameter**, not an automatically solved ion-energy PDE. For `e`, the
  New-only record uses `8/3` eV: the existing S6 initial mean energy 4 eV
  expressed as an effective Maxwellian temperature. In full New-only
  `[Energy]` mode, `log_e_energy` is auto-created and its IC is
  `E_{e,0}^{molar} = (3/2) (n_{e,0}/N_A) T_{e,0}[eV]`. The New-only
  S6 preflight rejects a competing Native electron energy variable/IC;
  archived Hybrid/partial modes remain unaffected.
- `sticking_coefficient` is a species property in [0,1]; `1` for the
  characterized three ions **and electron** (preserving the existing
  electron sheath absorption), `0` for unselected neutrals.
  Electron wall flux continues to use the established ESWallFluxMaterial.
- `initial_number_density` is particles/m³ for selected continuity
  species; `null` for unselected neutral species. Only selected
  non-null entries create log-molar FV/FEM variable ICs.
- Wall gradient is **not a species field**. All selected FV ions use the
  single `[Plasmas] wall_gradient = adjacent_element` setting
  (alternative `face`). `adjacent_element` uses the sided neighboring
  element gradient of FEM potential; `face` evaluates the FaceArg
  gradient. Neither turns migration on/off. `migration_smoothing_width`
  lives exclusively in `[Continuity]`; absent/0 selects hard max(x,0).
  The electron FEM wall material retains its existing adjacent-element
  gradient treatment.

## Typed transport in all species

`transport_coef` is always an object, with `type`, `file`, `unit`.

- Electron: `{"type":"lookup","file":"../../Issue91_real_qvt_r3/r3_e0/electron_moments.txt","unit":"reduced","bounds_policy":"clamp"}`.
  Source-relative table path is anchored to the **JSON file directory**.
  The table consumes canonical `e_energy_eV` and live `pressure` /
  `temperature` Functors. Both gas quantities come exclusively from
  MOOSE `[Plasmas]`; no species-level gas aliases are accepted.
- Ions O2p, Om, Op: `{"type":"constant","file":"none","unit":"physical","mobility":10,"diffusivity":0.25851999786435537}`.
  The explicit **user-defined JSON values** reproduce the archived S6 Native
  constants for all three ions. The Species-owned `DDTransportMaterial`
  generates `<species>_mobility` and `<species>_diffusivity` Functors.
  No upstream Native ion coefficient Material is required. These are
  **physical** mobility [m²/(V s)] and diffusivity [m²/s], not reduced
  coefficients. The parser and P0 guard reject negative or nonfinite values.
- Other neutrals: `{"type":"none","file":"none","unit":"none"}` means no DD
  transport object; independently owned Navier–Stokes/neutral transport
  remains unchanged.
- `functor` mode remains available for other scenarios whose physical
  coefficients are genuinely supplied by an independent upstream Material.

`species.e.energy_transport_coef` is **forbidden** in new-only JSON.
Electron energy transport closure belongs in MOOSE
`[Energy] transport_coefficient = fluid`. Selecting `fluid` requests
`(5/3)*e_mobility` and `(5/3)*e_diffusivity` from the existing electron
lookup `DDTransportMaterial`, in addition to all full Energy equation
Kernels when `fem_potential` is supplied.

## Reactions and wall/BC ownership

- `equations` maps reaction IDs to the checked text of each equation.
  `reactions` defines stoichiometry (`reactants`/`products`) used to
  generate `S_<species>_molar`; energy-loss settings produce electron
  energy-source contributions. Elemental and charge conservation are
  validated before generating those Functors.
- The 3 ion Wall Materials consume each species' molar mass, temperature
  fallback and sticking coefficient. Their density, potential, mobility
  and `temperature` Functors are derived by the existing Physics Action.
- The new-only JSON declares `drift_diffusion_boundaries` with **five
  nonoverlapping physical groups**: `inlet outlet`,
  `plasma_electrode plasma_metal plasma_right`, `plasma_cover`,
  `plasma_wafer`, `plasma_focus_ring`. Each group contains BC
  objects directly (no `bcs` wrapper). **Each BC has only `type`;**
  no `sidesets` option or independently repeated `variable`, `factor`
  or flux Functor field exists in the new JSON.
- Ion general-wall names (`O2p_wall`, `Om_wall`, `Op_wall`) appear in
  both general groups. The parser **coalesces the matching typed records**
  across disjoint groups into a single MOOSE BC per name, with the union
  of their physical sidesets. Conflicting duplicate names, overlapping
  physical group keys, different types, and duplicate residual owners
  fail closed. Thus 23 JSON references produce **20 unique BC objects**:
  3 general + 9 dielectric FV ions; 4 electron + 4 electron-energy FEM.
  BC names supply Species IDs, from which C++ derives
  `variable=log_<species>` and canonical
  `<species>_wall_number_flux`. For `e_energy_*` it derives
  `log_e_energy` and `e_energy_eV`.
- **Units and sign are code-owned:** general ion `FVFunctorNeumannBC`
  translates particle number flux [1/(m² s)] into log-molar boundary
  flux [mol/(m² s)] using `factor = -1/N_A`. The negative sign is
  the established Neumann loss convention. Dielectric ion
  `FVLogMolarDielectricFluxBC` instead divides the *signed*
  particle flux by `N_A` inside its residual method, without a
  user-provided `factor`.
- The two general groups produce a merged five-sideset ion wall BC,
  while electron `e_wall`/`e_energy_wall` exist **only** in the
  `plasma_electrode plasma_metal plasma_right` group, not inlet/outlet.
  Each dielectric group has exactly 3 ion, 1 electron and 1
  electron-energy BC. This exactly preserves the Native S6 electron
  particle/energy sheath on cover, wafer and focus_ring without widening
  the inlet/outlet electron residual.
- The new ion wall Functors and **Physics-generated** electron
  `ESWallFluxMaterial` provide current/charge ledger inputs. S6 New-only
  now selects **full** `[Energy] fem_potential = potential`, so it creates
  `log_e_energy` Time, Transport, Joule and chemistry-energy Kernels,
  `e_energy_eV`, `n_e_physical` and the canonical
  `e_wall_number_flux`. The legacy electron-wall Material and the
  independent `electron_transport`, `mean_energy`,
  `electron_physical_density` owners must be retired in disposable
  Scratch to avoid duplicate Functor registration. The lower-D Native
  surface-charge equations remain, consuming unchanged
  `cover/wafer/focus_ring_net_surface_current_density` names.
- **Important Scratch cutover:** the 8 original Native electron/
  electron-energy FEM BCs and redundant electron Energy Time/Transport/Joule
  and Chemistry Kernels must be removed from the disposable Scratch input.
  Their consumers are generated by `DDContinuityEq`, `DDEnergyEq` and
  `PlasmasAction`. This is independent of the 14 Native ion FV Kernels
  and 12 Native ion FV BCs. Original historical files remain untouched;
  actual Scratch P2 and runtime producer/consumer reachability are HOLD.
- The original S6 solved pressure variable is **`p`**, not
  `pressure`. Scratch must rename its solver variable and all neutral
  velocity/mass/pressure consumers from `p` to `pressure`, and remove
  the old variable's `initial_condition`; `[Plasmas] pressure`
  provides the unique canonical `FVConstantIC`. Likewise
  `log_ne -> log_e`, `log_energy -> log_e_energy`,
  `mean_en_solved -> e_energy_eV` and
  `electron_wall_number_flux -> e_wall_number_flux` must be completed
  without leaving residual Native aliases or duplicate physical owners.
  Preflight now rejects these names for modern S6 new-only inputs.
- `pressure`, `temperature`, `wall_gradient` (root),
  `fem_potential`, FV species selection and
  `migration_smoothing_width` (Continuity), plus
  `fem_potential` and `transport_coefficient = fluid` (Energy)
  belong to MOOSE `.i` input.
  S6 has a solved FV variable `pressure` that already provides its live
  Functor; root pressure is that variable's initial condition, **not** a
  competing constant pressure Functor. Root temperature produces its
  canonical constant Functor.

## Compatibility and remaining gates

Existing flat-form Hybrid fixtures are deliberately still readable by the
parser, to avoid breaking archived tests and historical science workflows.
Final-run candidates use only the new object-form transport and normalized
species fields; retired flat wall fields are rejected in that mode.

These candidate JSON files are source-reviewed but **must not be treated as
executed S6-417/941 Native-free inputs**. Rebase lookup file paths appropriately
when Scratch staging changes directory layout. Actual C2 combined
`physics-opt --check-input`, 11-layer Native ion 26-object retirement,
producer/consumer reachability, exact-head CI, and scientific parity remain
separate gates. No P3 was initiated by this schema update.
