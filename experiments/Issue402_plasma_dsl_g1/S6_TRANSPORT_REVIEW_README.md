# Issue 402 S6 input review — 417 and 941

The full **merged, review-only plasma JSON** for each case is:

- `chemistry/review_s6_417_full.json`
- `chemistry/review_s6_941_full.json`

Each has all seven species, all eight independent reactions, signed
energy metadata and explicit electron/ion DD coefficient ownership. The
electron JSON entry reads `chemistry/e_transport.txt` relative to the
JSON file. `e_transport.txt` currently holds a **synthetic P2 smoke
table** copied from `physics_app/ci/electron_energy_lookup_response_smoke_table.txt`,
not a verified Boltzmann EEPF transport dataset. The independent public
Boltzmann 19-table inventory contains *reaction rates*, not mu/D moments.

The complete corresponding *Physics overlay text* is:

- `review_s6_417_input_overlay.i`
- `review_s6_941_input_overlay.i`

**These overlays are not standalone full 10-layer Native S6 inputs.**
To render the complete executable Native input, first materialize the
historical public staged 10-layer source inputs, apply exact checksum and
9-electron-source owner cutover, and remove the old Native electron
coefficient provider in scratch before activating this JSON. Otherwise
`electron_mobility`/`electron_diffusion` would have duplicate producers.
The current Chemistry P3 runner still uses the prior unmodified
Chemistry-only overlay and does NOT activate these review candidates.

The front-end does not need `require_json_transport`. `PlasmasAction`
infers DD coefficient ownership: if *any* JSON DD record is provided,
every active Continuity FEM/FVM species must have exactly one record.
A fully absent DD section means legacy Native owners, preserving S6
during staged migration. A partially specified DD section fails closed.

The file `plasma_auto_constant.json` was augmented with synthetic
ion coefficient records because its P2 density-pair fixture selects
FEM e and FV O2p/Om/Op. These are TEST VALUES ONLY.

**Not yet accepted:** actual S6 electron Boltzmann mu/D table,
existing Native ion-provider ownership parity, mean-energy coordinate,
transport energy closure (currently 5/3), compiled exact-head
P2 for the review JSON, and B/D P3 science comparison.
No P3 dispatched, no original S6 input changed. `SCIENCE_HOLD`.

## Canonical Material naming update

JSON `model=functor` contains no explicit source keys. The material
looks for `O2p_mobility`/`O2p_diffusivity`,
`Om_mobility`/`Om_diffusivity`, and
`Op_mobility`/`Op_diffusivity` from an upstream producer. New
`DDMaterial` instances never register a duplicate output for
these canonical external Functors. `e_energy: {"type":"fluid"}`
explicitly selects the 5/3 energy closure. No science cutover is
authorized by this JSON schema change.

## JSON schema note

The reaction keys are `units` and `energy_loss_eV` (nonnegative
loss magnitudes). The Chemistry aggregate applies a minus sign to
electron-energy RHS terms, including positive-loss input Functors.
The review overlay has **no** `[FunctorMaterials]` section: DD species
coefficients are selected from JSON and built via `DDContinuityEq`/
`DDMaterial`. Existing Native kinetic progress Functors remain upstream.
The draft P3 runner still uses the historical 10-layer staged Native path
and has not activated the synthetic preview electron transport lookup.
