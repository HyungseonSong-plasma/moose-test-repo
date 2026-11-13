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
- `PhysicsIonWallTotalFluxMaterial` was **removed by parent PR #523**.
  It must not be restored to PhysicsApp. The scratch S6 D cutover migrates
  verified legacy total-only instances to active `PhysicsIonWallFluxMaterial`
  with `species_id`, replacing the old prefixed output names. Physics
  parameters are retained; numerical parity is a separate science gate.
- `PhysicsElectronWallFluxMaterial` and
  `PhysicsElectronAdjacentSheathWallFluxMaterial`: `species_id = e` opts
  into canonical electron names; absent preserves legacy names. Any other
  electron species ID is rejected.
- `PhysicsPlasmaChargeDensityMaterial`: `canonical_species_names = true`
  selects `<species>_number_density` instead of
  `ion_number_density_<species>`; default false preserves old consumers.
- Only one producer for each public Functor. The retired total-only owner
  must not be instantiated in current Native inputs.
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
4. Replaces the retired total-only ion Material type with the active
   `PhysicsIonWallFluxMaterial` **in scratch only**, adds `species_id`,
   removes verified legacy `output_prefix` and rewrites BC, ledger and
   postprocessor references in all ten staged D layers.
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


## Verified public S6 input replay (P0 evidence; no Native full S6 acceptance)

The checked public S6 archive at
`experiments/Issue493_s6_boltzmann/public_p2_decks.tar.xz.b64`
(pack SHA-256 `9e801cc6dca3860750b7b97fb6ceca8e6060a3c894dd616cbaf688f529fea240`)
was examined across both B/C variants for S6-417 and S6-941. The C
candidate base layers contain exactly four compatible Wall FunctorMaterials:

- `PhysicsIonWallTotalFluxMaterial` for O2p (existing
  `n_i_physical`), Om (`output_prefix = negative_` and
  `n_m_physical`), and Op (`output_prefix = atomic_positive_` and
  `n_op_physical`);
- `PhysicsElectronAdjacentSheathWallFluxMaterial` for electron
  collection, preserving the original physical sheath formula.

The associated consumer interfaces include `functor`,
`wall_number_flux`, `signed_number_flux`, `surface_current_density`
and multi-input `functor_names`. Their *values* are rewritten along with
the owning source. Diagnostic object identifiers such as
`d1_electron_mean_speed_m_s` are not equivalent to the public Functor
`electron_mean_speed` and must remain untouched.

P0 reproduced the naming cutover **in memory on all 11 public C input
layers per case**, verified four unique species-owned sources,
checked the expected renamed BC/surface references and left the B and C
archive bytes unchanged. The replay test and eight synthetic cases
passed [Actions #43311612385](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43311612385)
(10 tests PASS). The earlier exact-head P0/P1/P2-only construction job
passed [Actions #43309999844](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43309999844)
(22 P0 tests PASS, native P1 PASS, synthetic wall P2 PASS).

These two run heads are pre-cleanup evidence identities. Their one-shot
workflow files have since been removed without changing the production
C++ or staging logic. Neither run establishes full **S6-417/941 Native
P2** acceptance or physical parity; the inherited P2 HOLD and
`SCIENCE_HOLD` remain. No full S6 timestep/P3 has been run.

## Parent PR #523 retirement reconciliation

At parent HEAD `ed608a23f79fe25e31041b184fa27edb21ba7385`, the duplicate `PhysicsIonWallTotalFluxMaterial.C` was removed. Parent test `tests/test_retired_legacy_physics_owners_contract.py` requires it to remain absent. The active six-output `PhysicsIonWallFluxMaterial` already implements thermal surface + migration total number and mass fluxes with corresponding input roles and defaults. This cutover changes *only* disposable S6 D scratch type declarations and canonically owned output names, with density/charge/prefix guards. The B/C archives stay immutable. Source-level mathematical equivalence must be independently verified before scientific acceptance; construction P2 does not prove numerical parity.


## Exact-parent source reconciliation and P0/P1/P2 revalidation

- Parent Draft PR #523 exact HEAD: `ed608a23f79fe25e31041b184fa27edb21ba7385`.
- Child Draft PR #524 was synchronized through a **non-force**
  two-parent merge commit `dd1aea50569e6866b1f70c636f8aa43661ec19db`.
  The reconciled tree preserves all parent deletions, notably
  `PhysicsIonWallTotalFluxMaterial.C`, and carries only the nine
  species-naming source/test/doc files as the PR-level diff.
- Scratch S6-417/941 old `PhysicsIonWallTotalFluxMaterial` blocks are
  replaced with the live `PhysicsIonWallFluxMaterial`, with validated
  original density, charge, temperature and mobility inputs, new
  `species_id`, and consumer Functor references. The original archived
  C/B inputs are not changed. No retired factory source is reintroduced.
- [Exact-head run #43328122988](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43328122988)
  at `0d940fbd096990977b8ba592177c1f10a274aa06`: **27 P0 tests PASS**,
  Native **P1 PASS**, native three-ion (O2p/Om/Op) plus electron Wall
  **P2 `--check-input` PASS**, `Syntax OK`. The run includes the parent
  retired-owner contract, full public S6-417/941 *in-memory* cutover test,
  source ancestry check, and no-solve policy.
- The validation-only workflow was removed afterward; this documentation
  update does not change C++ or migration implementation. Post-cleanup
  commit is a different SHA and must not be misidentified as the binary
  source SHA from the run.
- Full **S6 Native P2** source/rate/mesh construction is still separate
  and was **not run** by the Wall naming workflow. No P3 science solve,
  numerical parity, merge, or promotion. `SCIENCE_HOLD` stays active.


## Independent review and full S6 native P2 closeout

- CodeRabbit independent review of Draft PR #524: [review
  #5883798421](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/524#pullrequestreview-5883798421).
  **Major** electron wall source-identity weakness was fixed by validating
  `electron_density` against predeclared electron Functor names
  `n_e_physical`, `n_e`, and `e_number_density` before any scratch
  rewrite. Negative tests reject `n_Om`, `n_m_physical`, and unknown
  electron densities. The exact code P0 run
  [#43331778712](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43331778712)
  passed **573 tests** at source
  `ab72bacf98a1c20b5c90e8853095a677c4869253`.
- The review's one-shot CI trigger concern is resolved operationally by
  removing the one-shot workflows after their bounded runs. They are not
  continuous validation, and any later code revision requires a fresh
  exact-head check. The review also identifies a significant *unverified*
  semantic gate: Python-only analytical equivalence does **not** evaluate
  the C++ Functor at native face arguments. Both ion charge signs and
  oriented normals need a true native regression or independent review
  before authorizing a merge that requires full semantic compatibility.
- [Real public S6-417/941 Native P2 run
  #43330062471](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43330062471)
  at `7ef837c29e4587418ab5975f1323db2372ab7d85`:
  P0 570 PASS, public 400 W mesh preparation PASS, Native P1 PASS,
  both actual eleven-layer S6 `--check-input` **HOLD**
  (`NATIVE_CHECK_INPUT_REJECTED`, exit 1). Original B/C archives
  were never modified; P3/P4 NOT_RUN.
- [Raw-log diagnostic retry
  #43331410674](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43331410674)
  at `8abe68eeccfbe44d78c3cbddf554c472800a7ac9`
  reproduced both failures. The *first actual native parser error in both*
  was `A 'PhysicsElectronTransportLookupMaterial' is not a registered object.`
  The original archived name's factory alias is intentionally retired by
  `physics_app/ci/check_plasma_closures_contract.py`; it is no longer
  a live C++ Material. `DDMaterial` now owns lookup coefficients, but
  its `model=lookup` / `table_file` / `mean_en_solved` contract
  requires separately verified input/physics ownership and is **not**
  assumed identical to the retired old factory. Do not restore the alias
  or silently substitute a new transport law.
  Exact Native logs + sanitized P2 status are preserved in
  [artifact #13994449104](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43331410674/artifacts/13994449104).
- The controller handoff was admitted as central
  [Samuel Issue #315](https://github.com/HyungseonSong-plasma/chatgpt-operation/issues/315).
  Its requested merge is strictly **PR #524 into parent branch
  `issue-402-chemistry-json-energy-charge`**, not into `main`. It is
  conditional on independent review, actual native semantic parity,
  exact-head P0/P1 and full S6 Native P2, plus registered cross-repository
  merge authority. Controller must fail closed if any gate remains open.
- No one-shot workflow is retained in the branch. Source work performed
  in this turn is confined to a safeguarded electron density ownership
  check, its negative tests and this evidence note.
  **No merge; `SCIENCE_HOLD`; P3/P4 NOT_RUN.**


## 2026-11-13 operator scope update: D1 observation is obsolete

The user confirmed Issue397 lower-D D1 face-current and geometry AuxKernels
were **temporary debugging instrumentation** and are no longer needed now
that the issue they were introduced to diagnose has been identified.
This explicit operator decision supersedes prior PR #524 D1-only blocking
language about 14-probe FaceArg/oriented-normal/field reproduction, diagnostic
numerical parity and optional independent review of D1 retirement.
None of these *obsolete diagnostic* criteria is a current acceptance gate.

The disposable D scratch input permanently retires only the 14 archived D1
AuxKernel owners and their 14 self-contained AuxVariables after strict
exact-signature/external-consumer checks. Archived B/C files stay immutable.
The actual supported physics Kernel `PhysicsLowerDSurfaceCurrent` and all
Wall, RF, charge, electron-transport and Chemistry ownership remains active.
No debug observer is re-registered or silently emulated.

[Earlier core Native run #43407079646](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43407079646)
had 638 P0 passes, fresh Native P1 PASS and S6-417/941
`physics-opt --check-input` both `Syntax OK`; it was labelled
`CORE_INPUT_P2=PASS` at the time because debug reproduction was still
pending. Now the intended *active S6 physics input* explicitly excludes
the obsolete D1 diagnostics, so this existing P2 evidence applies to that
selected input scope. The historical run and its receipts are not changed.

This scope update does **not** waive actual physical Native face-value
numerical parity or approval requirements imposed by repository protections,
and does not authorize P3, merge or any science acceptance. Keep
`SCIENCE_HOLD` and Draft PR status pending those distinct gates.

Active input exact-head P2 evidence after operator decision: [run #43416474682](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43416474682) on `44b2ba1c2784ae33e5adad6388b5cd4783de7f24` records 638 P0 PASS, Native P1 PASS, S6-417 and S6-941 `--check-input` Syntax OK / exit 0. `ACTIVE_MODEL_P2=PASS`; retired D1 diagnostic parity `NOT_APPLICABLE` and independent D1 retirement review `NOT_REQUIRED_OPERATOR_DECISION`; P3 `NOT_RUN`, `SCIENCE_HOLD`, no merge. Signed evidence: [artifact #14033140207](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43416474682/artifacts/14033140207). Scientific parity remains separate.
