# Issue #402: JSON Chemistry heavy/surface rate unification

**Status:** Draft implementation. Native P1/P2 and numerical equivalence are
separate acceptance gates. `SCIENCE_HOLD`; no production P3 authorization.

## Data authority

`Plasma::ChemistryData` in `Chemistry.h/.C` is the sole active parser for
H01–H05 heavy-particle and optional surface-reaction data. The old free-form
text parser and its header/source are not registered, aliased, or shipped.
The old `PhysicsReactionRateMaterial` and `PhysicsSurfaceReactionMaterial`
classes, files, and factory names are removed, with **no** factory alias.

The active calculation-only owners are:

- `HeavyReactionRateMaterial`: computes molar progress `R_H01`–`R_H05`
  using the canonical JSON mechanism and explicit density, temperature, and
  mass-fraction Functors. Does not recompute electron-impact rate tables.
- `SurfaceReactionMaterial`: computes an opt-in, neutral,
  `thermal_sticking` progress `R_Hnn` and signed outward
  `surface_mass_flux_<species>`. Charged wall flux has a separate physics
  owner and is not silently activated.

`[Plasmas]/files` and the explicit material `chemistry_file` refer to the
**same JSON schema and parser**. Standalone historical Stage-5 runtime
fixtures use `chemistry_file`; Chemistry Physics uses the shared
`PlasmasAction` catalogue. Existing electron-impact channels may omit
`rate` to indicate that their progress has an independently owned kinetic
table. Chemistry projects a volume reaction only once into species and
electron-energy sources; surface reactions are excluded from volumetric
source generation.

## JSON rate schema

Each species involved in a mass-fraction-driven rate has
`molar_mass_kg_mol` in addition to `elements` and `charge_number`.
A reaction has canonical `id`, `reactants`, `products`, matching
`equations[id]`, `units`, and explicit `energy_loss_eV`.

For a heavy volume channel:

```json
{
  "id": "H01",
  "domain": "volume",
  "units": "mol/(m^3 s)",
  "reactants": {"Op": 1, "O2": 1},
  "products": {"O": 1, "O2p": 1},
  "energy_loss_eV": {"model": "none"},
  "rate": {"model": "power_law", "A": 2e-17, "basis": "particle",
           "T_ref": 300, "exponent": 0.5}
}
```

`rate.model` accepts `constant` and `power_law` in a volume reaction.
Power-law temperature scaling is exactly `(T_ref/T)^exponent`.
For a reaction order `m`, the particle basis is converted **once**:

`A_molar = A_particle * N_A^(m - 1)`.

`R_H = A_molar (T_ref/T)^exponent product(c_i^alpha_i)`,
`c_i = rho * Y_i / M_i`, `R_H` in mol/(m^3 s).
Input `A`, `T_ref`, `exponent`, molar mass, and sticking values must be
finite and physically admissible. Invalid models, fields or mismatched units
fail closed. Electron-impact Progress is not re-evaluated here.

For a surface reaction, use `domain: "surface"`,
`units: "mol/(m^2 s)"`, and
`rate: {"model":"thermal_sticking","sticking":0.25}`.
The neutral incident molar flux is `c sqrt(8 R T/(pi M))/4`, with
`R_surface = sticking * incident_flux / reactant_coefficient`.
Mass flux is `J_species,out = -M_species sum(nu * R_surface)`.
`deferred_charged_flux` may be declared but is **never** executed by the
neutral sticking material.

## Stage-5 migration and immutable evidence

- H01–H04: `stage5_s5d_oxygen_heavy.json` preserves all four original
  coefficients, exponents, stoichiometries, charge, oxygen inventory, and
  particle-basis Avogadro conversion.
- H05: `stage5_s5e_h05_oxygen_heavy.json` preserves
  `Om + O -> O2 + e`, `A=3e-16` particle basis, exponent zero,
  explicit zero electron-energy source, and separate electron particle
  projection.
- Active Stage-5 and S5-R input generators switch to
  `HeavyReactionRateMaterial`, JSON files, and `R_Hnn` names.
- Historical frozen Stage-5 contract JSON and B/C original archives retain
  their source-era names and audit hashes. They are provenance, **not**
  a request to restore old registrations.

## Gates

P0: JSON contract, rate-law parity, H01–H05 analytic oracles, S5-R source
owner assembly, negative parser controls, and absence of all legacy files.

P1: compile the exact branch head using the pinned MOOSE image.

P2: same-binary `--check-input` for H01–H04, H05, and synthetic neutral
sticking. This proves construction only.

P3 / scientific parity: **NOT AUTHORIZED** for this change. No wall
face-value or full S6 trajectory equivalence is implied by P2. No merge
into the parent branch or `main` until exact-head evidence is reviewed.
