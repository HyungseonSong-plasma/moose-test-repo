# Issue #402 — JSON-owned transport coefficients and automatic Physics binding

**Draft/implementation checkpoint; not accepted S6 physics.** All transport
coefficients are defined in the ordered mechanism JSON files referenced by
`[Physics]/[Plasmas]/files`. Neither `DDContinuityEq` nor `NVTransport`
exposes table paths, mobility/diffusivity constants, or coefficient choices
in its public MOOSE Physics block.

## JSON contract

```json
{
  "species": {
    "e": {"elements": {}, "charge_number": -1},
    "O2p": {"elements": {"O": 2}, "charge_number": 1},
    "O2": {"elements": {"O": 2}, "charge_number": 0},
    "O": {"elements": {"O": 1}, "charge_number": 0}
  },
  "equations": {},
  "reactions": [],
  "transport_coefficients": {
    "drift_diffusion": {
      "e": {
        "model": "lookup",
        "table_file": "tables/electron_transport.txt",
        "table_units": "reduced",
        "pressure": "p",
        "gas_temperature": "T_g",
        "bounds_policy": "error"
      },
      "O2p": {
        "model": "constant",
        "mobility": 0.1,
        "diffusivity": 0.01
      }
    },
    "navier_stokes": {
      "transport_data_file": "tables/heavy_collision_database.txt",
      "temperature": "T_g",
      "pressure": "p",
      "species": ["O2", "O"],
      "mass_fractions": ["Y_O2", "Y_O"]
    }
  }
}
```

**The numbers and paths above illustrate syntax only**; no physical S6
coefficient values are asserted.

Each charged particle (including electrons and ions) can own a distinct
`drift_diffusion` table. The resolved table path is **relative to the JSON
file that declares it**, not relative to the current MOOSE input, process
working directory, or another JSON file. Absolute paths are accepted if
available in the execution environment. Paths are checked for readability.

- `model=constant` requires finite, nonnegative `mobility` in m²/(V·s)
  and `diffusivity` in m²/s. It prohibits lookup settings.
- `model=lookup` requires one three-column `table_file` and a
  implicit `mean_en_solved` coordinate Functor. `table_units=reduced` means columns are `mu*N_n`
  and `D*N_n`; it requires `pressure` [Pa] and `gas_temperature` [K] to
  calculate `N_n=p/(k_B*T_g)`. `table_units=physical` consumes table
  values directly. `bounds_policy=error` (default) rejects out-of-range
  lookup; `clamp` is explicit.
- `navier_stokes.transport_data_file` is the **existing** NV collision
  database, plus its driving temperature, pressure, species and mass fraction
  Functors. Charged-pair NV inputs may additionally specify both
  `electron_temperature` and `electron_number_density`.

The ChemistryData parser merges the ordered `files` list. Across files,
multiple declarations for one DD species or one NV owner must be identical
after path resolution. Conflicting definitions, unknown species, missing
required fields, unsupported models, and invalid/missing tables fail.
Reactions and signed channel energy losses are unchanged.

## MOOSE input

```ini
[Physics]
  [Plasmas]
    files = 'chemistry.json'
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e'
          fvm_species = 'O2p'
          fem_potential = potential
        []
      []
      [NavierStokes]
      []
    []
  []
[]
```

`DDContinuityEq::addFunctorMaterials` walks FEM species followed by FVM
species and generates one `DDMaterial` for each species with a JSON
`transport_coefficients.drift_diffusion` record. It publishes
`<species>_mobility`, `<species>_diffusivity` and the existing 5/3
electron-energy transport projection for `e`. Its existing FEM-generated
continuity kernels continue to resolve these exact coefficient Functors;
FVM transport equations themselves are **still Native-owned**, not generated.

`NVTransport::addFunctorMaterials` binds the JSON-defined heavy collision
database and metadata into one `NVMaterial` when the empty
`[NavierStokes]` Physics tag is enabled. No transport-specific
`[FunctorMaterials]` blocks are needed. Independent state/thermodynamic
or reaction-rate Functors are **not** transport coefficients and remain
separate responsibilities.

## Migration and physics safeguards

- For physical S6-417/941, the original nonconstant electron/ion transport
  providers and archived rate files remain scientific evidence. This PR
  deliberately **does not** invent a lookup table, mobility or diffusivity
  in `oxygen_s6_common.json`. Existing Native coefficient sources continue
  to work for species without a new JSON DD entry during the transition.
  Production S6 auto-binding for every species requires separately verified
  actual coefficient tables and provider de-duplication, followed by
  numerical parity; this is not implied by P2.
- Synthetic P2 fixture files `plasma_auto_constant.json`,
  `plasma_auto_lookup.json`, `plasma_auto_navier_stokes.json` and
  `chemistry/oxygen_s6_p2_transport.json` contain illustrative data
  **only** for parser/action construction. They are never physical input.
- Do not add a second provider of a canonical species mobility or diffusion
  Functor; preserve original AD derivative, sign, unit and energy 5/3.
- P1 compilation, P2 input checks, representative coefficient/AD derivative
  numeric comparisons, original S6 source-owner replay, and S6 transport/
  chemistry parity are independent gates. No P3 and no merge while
  `SCIENCE_HOLD` applies.

**Schema update (2026-11-12):** `coordinate`,
`mobility_source`, and `diffusivity_source` must not appear in
backend-generated JSON DD entries. The model-only `functor` mode
resolves canonical species names inside `DDMaterial`, preserving
AD coefficients without duplicate producers. Use
`e_energy: {"type":"fluid"}` for the 5/3 electron-energy transport
closure. The previous syntax above is retained only as historical
discussion where applicable.
