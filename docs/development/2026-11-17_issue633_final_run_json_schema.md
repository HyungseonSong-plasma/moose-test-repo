# Issue #633 — S6 New-only single-file run JSON candidate

Status: **PROPOSED SCHEMA, NOT P2/SCIENCE ACCEPTED**. The active draft integration
PR #665 contains the candidates. Historical Hybrid S6 sources and runner remain unchanged.

## Exact files

- `experiments/Issue402_plasma_dsl_g1/chemistry/unified_s6_417_newonly.json`
- `experiments/Issue402_plasma_dsl_g1/chemistry/unified_s6_941_newonly.json`

Each file contains seven species, eight pinned reaction entries, **two grouped**
drift-diffusion boundaries. They instantiate 12 ion FV BC objects and 8
electron/energy FEM sheath BC objects without changing the historic
electron's inlet/outlet boundary treatment. The source has one electron
surface-current selector. There is **no synthetic progress rate** in
either file. Eight live `R_*` progress producers and all upstream coefficient
Functors must be available in a staged new-only Scratch input before P2.
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
    "type": "functor",
    "file": "none",
    "unit": "physical"
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
  expressed as an effective Maxwellian temperature. Only when
  `log_e_energy` is auto-created does this provide its IC via
  `E_{e,0}^{molar} = (3/2) (n_{e,0}/N_A) T_{e,0}[eV]`. A retained Native
  `log_e_energy` variable continues to own its existing IC.
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
- Ions O2p, Om, Op: `{"type":"functor","file":"none","unit":"physical"}`.
  C++ derives `<species>_mobility` and `<species>_diffusivity`. The pinned
  original S6 Native coefficient providers supply **physical** values.
  Writing `unit:"reduced"` here would falsely assert N-scaled transport
  that the Functor Material does **not** convert and is rejected.
- Other neutrals: `{"type":"none","file":"none","unit":"none"}` means no DD
  transport object; independently owned Navier–Stokes/neutral transport
  remains unchanged.
- `constant` mode remains supported for synthetic fixtures via the same
  object plus numeric `mobility` and `diffusivity`, `file:"none"`,
  `unit:"physical"`.

Only `species.e` additionally declares `energy_transport_coef:"fluid"`,
because it owns the separately selected electron-energy physics.

## Reactions and wall/BC ownership

- `equations` maps reaction IDs to the checked text of each equation.
  `reactions` defines stoichiometry (`reactants`/`products`) used to
  generate `S_<species>_molar`; energy-loss settings produce electron
  energy-source contributions. Elemental and charge conservation are
  validated before generating those Functors.
- The 3 ion Wall Materials consume each species' molar mass, temperature
  fallback and sticking coefficient. Their density, potential, mobility
  and `temperature` Functors are derived by the existing Physics Action.
- The new-only JSON declares `drift_diffusion_boundaries` with **two**
  sideset groups. Each group contains BC entries directly (no `bcs`
  wrapper), each specifying only `type` and optionally `sidesets`
  to restrict an entry to a subset of that group. BC names supply
  species IDs, from which C++ derives `variable=log_<species>` and
  canonical `<species>_wall_number_flux`. For `e_energy_*` it derives
  `log_e_energy` and `e_energy_eV`.
- **Units and sign are code-owned:** general ion `FVFunctorNeumannBC`
  translates particle number flux [1/(m² s)] into log-molar boundary
  flux [mol/(m² s)] using `factor = -1/N_A`. The negative sign is
  the established Neumann loss convention. Dielectric ion
  `FVLogMolarDielectricFluxBC` instead divides the *signed*
  particle flux by `N_A` inside its residual method, without a
  user-provided `factor`.
- The general five-side group has ion `*_wall` objects and electron
  `e_wall`/`e_energy_wall` objects, but the electron pair is
  restricted explicitly to `plasma_electrode plasma_metal plasma_right`
  (not inlet/outlet). The three dielectric sides remain separately owned
  by 9 ion, 3 electron, and 3 electron-energy BC entries; each uses
  `sidesets` to select its actual physical surface.
- The same new wall-flux Functors feed the three surface-current
  properties. The electron sheath publishes `e_wall_number_flux`
  via the existing `ESWallFluxMaterial` with `species_id=e`. The
  lower-D Native surface-charge equations remain permitted if no
  producer collision exists.
- `pressure`, `temperature`, `wall_gradient` (root),
  `fem_potential`, FV species selection and
  `migration_smoothing_width` (Continuity) belong to MOOSE `.i` input.
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
