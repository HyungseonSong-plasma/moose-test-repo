# Issue #402 — Species-first public Functor naming contract

**Scope:** stacked implementation cut over Draft PR #523 (Chemistry/DD/charge).
**Evidence:** source/P0 and new Native P2 construction input; no numerical parity
claim, no accepted science gate, no merge, `SCIENCE_HOLD`.

## Boundary

Canonical names are **public Functor providers** and **their consumer values**.
`ion_number_density`, `electron_density`, `potential`, `mobility`, and
`mean_energy` are **role-based InputParameter keys**, not public Functor
identity names. They must stay generic so that the same Material class can
consume any selected species through explicitly named Functors.

Use the same solver-safe Chemistry/JSON species ID, beginning with a letter and
then alphanumeric/underscore characters, without deriving names from a
display label or the obsolete `ion`/ `electron` coarse identifiers.

| Quantity | Canonical producer / consumer | Legacy producer |
| --- | --- | --- |
| Mobility | `<species>_mobility` | `ion_mobility`, `electron_mobility` |
| Diffusivity | `<species>_diffusivity` | `ion_diffusion`, `electron_diffusion` |
| Heavy number density | `<species>_number_density` | `ion_number_density_<species>` |
| Ion total wall number flux | `<species>_wall_number_flux` | `ion_wall_number_flux` |
| Ion total wall mass flux | `<species>_wall_mass_flux` | `ion_wall_mass_flux` |
| Ion thermal surface number/mass | `<species>_wall_surface_number_flux`, `<species>_wall_surface_mass_flux` | `ion_surface_*_flux` |
| Ion migration number/mass | `<species>_wall_migration_number_flux`, `<species>_wall_migration_mass_flux` | `ion_migration_*_flux` |
| Electron wall number flux | `e_wall_number_flux` | `electron_wall_number_flux` |
| Electron mean speed | `e_mean_speed` | `electron_mean_speed` |
| Electron sheath drop | `e_wall_sheath_drop_V` | `electron_sheath_drop_V` |

`mean_en_solved` (electron energy lookup coordinate), `S_<species>_molar`
(Chemistry source), `R_<reaction ID>` (Chemistry progress),
`charge_density`, and `poisson_charge_source` have their own distinct,
already-established domain contracts. They are **not** automatically renamed
by the wall-transport naming change.

## Compatibility and activation

- `PhysicsIonWallFluxMaterial`: providing `species_id = O2p` switches
  all six wall Functors to canonical names; absent `species_id` preserves all
  six existing legacy names and equations.
- `PhysicsIonWallTotalFluxMaterial`: `species_id` switches the two outputs
  to canonical names; `output_prefix` is a legacy-only option and is
  rejected in combination with `species_id` to avoid unpredictable names.
- `PhysicsElectronWallFluxMaterial` and
  `PhysicsElectronAdjacentSheathWallFluxMaterial`: `species_id = e` opts
  into canonical electron names; absent preserves legacy names. Any other
  electron species ID is rejected.
- `PhysicsPlasmaChargeDensityMaterial`: `canonical_species_names = true`
  selects `<species>_number_density` instead of
  `ion_number_density_<species>`; default false preserves old consumers.
- One producer of each public Functor name per active scope. Do not instantiate
  both ion wall Material variants for the **same** canonical species/output.
- BC object blocks may be named `[O2p_wall]` or `[e_wall]`, but each BC's
  `functor` input must select `<species>_wall_number_flux` and the
  corresponding `log_<species>` equation; no inference from BC block name.
- No aliases are silently installed when canonical mode is selected. Legacy
  inputs and immutable S6 references retain their original byte-level names.

## Construction evidence

- Positive two-ion plus electron fixture:
  `physics_app/ci/species_wall_functor_naming_smoke.i`, P2
  `physics-opt -i ... --check-input` only, not P3.
- P0 source and wiring checks with a swapped-species negative control:
  `tests/test_issue402_species_functor_naming.py`.
- Native P1/P2 at the **new exact HEAD** is still required. PR #523 had an
  inherited pre-existing S6 P2 HOLD; do not attribute or clear that gate with
  a naming-only static check.
- Explicitly prohibit full S6 physics P3, wall-law/sign/unit changes,
  history rewrites, and promotion to stable/default until independent
  equivalence and existing issue #402 gates are accepted.

## Next cut after acceptance

Inventory all production and scratch-only new-run BCs, FV Kernels, and
postprocessor consumers. Replace only new-run value bindings (including
selected electron wall providers); keep historical input names as evidence.
Native/physics acceptance remains separated by P0 -> P1 -> P2 -> P3.


## #524: New S6 D scratch-only Wall producer/consumer cutover

The active Chemistry staging owner is
\`experiments/Issue402_plasma_dsl_g1/chemistry/prepare_s6_run_input.py\`.
The path operates on the ten disposable S6 D layers and overwrites the
scratch \`migrated_continuity.i\` overlay only after prewrite validation.
The original historical S6 archive, B/C controls and preserved evidence
are immutable. No new wall law, state equation or boundary is generated.

After the existing Chemistry and electron-state renames, the Wall cutover:

1. Inventories registered \`PhysicsIonWallFluxMaterial\`,
   \`PhysicsIonWallTotalFluxMaterial\`, \`PhysicsElectronWallFluxMaterial\`,
   and \`PhysicsElectronAdjacentSheathWallFluxMaterial\` providers in staged
   \`[FunctorMaterials]\`. Unrecognized or unsupported original wall factories
   do not receive guessed canonical identities.
2. Checks output-prefix and physical species source: \`ion_wall_flux\`
   maps to \`O2p\` only with a predeclared O2p density name and charge +1;
   \`atomic_positive_\` to \`Op\` (charge +1); \`negative_\` to \`Om\`
   (charge -1). Only the recognized \`electron_wall_flux\` maps to \`e\`.
3. Rejects duplicate producers for an old output and any consumer of a
   legacy wall output whose producer cannot be proven. No partial file write
   occurs when an owner fails the gate.
4. Adds \`species_id\` to each verified staged source, removes a verified
   legacy \`output_prefix\` only when required, and rewrites references in
   BCs, charge ledgers and postprocessors across the ten D scratch layers.
5. Returns producer identity, renamed consumer counts and
   \`P3=NOT_RUN\` / \`SCIENCE_HOLD\` in
   \`scratch_wall_functor_cutover\`. A zero-owner no-op is reported
   explicitly rather than claiming an S6 migration.

This is an **opt-in new-run staging cutover**. It does not rename the
historically accepted Issue #3, #27 or #395 producers in their committed
source inputs. An archival upstream type/alias not supported by the current
Wall Material classes must be classified and separately resolved; the
script must HOLD rather than accepting an unsafe string-only migration.

P0 cases cover two positive ions, one negative ion, electron sheath,
shared charge-ledger and BC consumers, duplicate source identity, source
charge/density mismatch, unsupported QPX producer, and unknown prefixes.
The synthetic P0 test is not full archival S6 P2. The prior inherited
S6-417/941 P2 issue remains open until its separate exact-head construction
gate passes. No P3 was requested or authorized.
