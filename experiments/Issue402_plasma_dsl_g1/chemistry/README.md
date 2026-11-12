# Issue #402 — S6 Chemistry run-input preparation (not scientific acceptance)

## What these files are

- `oxygen_s6_common.json`: **7** archived shared reaction channels (EI-02, EI-17,
  EI-415, EI-401, EI-407, EI-2069, H25) and the validated species/charge catalogue.
- `oxygen_s6_417.json`: **one** EI-417 ionization channel, -17.0 eV/event.
- `oxygen_s6_941.json`: **one** EI-941 ionization channel, -13.62 eV/event.
- `../s6_417_chemistry_run.template.i` and `../s6_941_chemistry_run.template.i`:
  exact MOOSE input overlays intended to **replace** (not append to)
  `migrated_continuity.i` when a full archival S6 stack has been scratch-staged.
- `prepare_s6_run_input.py`: strictly bounded scratch-only source-owner cutover.

The original pinned source of channel equations, historical rate Functor names and
electron-energy loss data is the archived S6-417/941 input sequence from Issue
#477. The input files are unchanged. Kinetic rate tables and any private data
are **not** embedded here. Their original progress Functor providers must
still be supplied by the staged S6 native input layers.

## Inputs and source signs

Each selected S6 mechanism contains **8** reaction IDs. All reaction progress
Functors have `mol/(m^3 s)` units. The JSON no longer repeats `progress`:
`Chemistry.C` derives `EI-02 → R_EI02`, `EI-415 → R_EI415`,
`EI-2069 → R_EI2069`, `H25 → R_H25` deterministically from the ID.
For the archived S6 inputs, the scratch-only preparation step renames
all existing progress provider definitions and consumers (`R_elastic_O2`,
`R_elastic_O`, `R_ion_O2`) directly to `R_EI02`, `R_EI17`,
`R_EI415`. No temporary rate alias Materials are used and the underlying
kinetic expressions, units and numerical values are unchanged. A negative
`electron_energy_change_eV` represents electron energy lost.

- EI-02 and EI-17: source-defined **variable** elastic loss magnitude
  `delta_epsilon_EI02_eV` / `delta_epsilon_EI17_eV`. Each input template
  creates a new signed Functor equal to the **negative** of that value.
- EI-415: -12.06; EI-401: 0 (explicit, unchanged); EI-407: -0.977;
  EI-2069: -5.02 eV/event.
- EI-417: -17.0 **or** EI-941: -13.62 eV/event.
- H25: `model: none` for **electron-energy** exchange. Its unresolved
  ion-neutral energy partition remains under `SCIENCE_HOLD`; do not interpret
  `none` as an accepted complete energy model.

The `[Energy]` DSL has no `variable` option. `DDEnergyEq` resolves
`log_<species>_energy`, i.e. `log_e_energy`, internally. The scratch cutover
renames all existing `log_energy` variable references to `log_e_energy` in
disposable layers; this does **not** mean the solver variable is auto-created.
It still must exist in the staged input variables.

The `Chemistry` Physics builds **one** aggregate `Q_e_molar_eV` from all
channels; `DDEnergyEq` applies it once on the RHS.
`DDContinuityEq` applies `S_e_molar` once. Existing RF heating, Joule
heating, charged-species FV source and momentum/pressure ownership are **not**
included in the electron-only cutover and remain exactly where previously
defined. Source units, duplicates, constrained O2, source ownership and
numerical B-vs-D parity require independent checks.

## Scratch-only preparation contract

1. Stage the 10 **unmodified** historical native S6 input layers plus the
   existing C/D `migrated_continuity.i` using Issue402's established staging
   process. Do **not** alter historical B/C or any pinned artifact.
2. Perform the canonical solver-state replacement and retired FEM type remap
   **only on scratch D copies**. Keep the list `ordered` of the 11 filenames.
3. In that scratch folder, call:

   ```python
   from pathlib import Path
   from experiments.Issue402_plasma_dsl_g1.chemistry.prepare_s6_run_input import prepare

   report = prepare(Path("/scratch/staged/experiments/Issue395_powered_chemistry_ladder"),
                    ordered, "417")  # or "941"
   ```

   Alternatively run the CLI with `--staged-chem-dir`,
   `--ordered-file` (JSON list of 11 filenames), `--variant` and
   `--report`.
4. This checks exact original source names, signed RHS setting, variables,
   block and functor identity. It removes only **9** obsolete electron
   particle/energy `FunctorKernel` objects (all seven other source and
   transport responsibilities remain unchanged), and replaces only the
   scratch `migrated_continuity.i` with the committed template. It copies
   exactly the two required mechanism files to `scratch/chemistry/`.
5. Run the exact-head `physics-opt --check-input -i <all 11 staged files>`
   **before any P3/native timestep**. Both S6 paths must pass. A separate
   static check uses the real archived input files and confirms the 9-source
   migration targets. The small `chemistry_s6_*_catalogue_p2.i` decks use
   **synthetic** progress values and verify the C++ JSON/equation/energy
   generation path; they are **not** physical rate replay.
6. Even after P2, full private-rate availability, rate/source provenance,
   equivalence of old-vs-aggregated electron/energy terms, charged-species
   FVM sources, numerical parity and the science gate must be approved
   **separately** before the migrated S6 deck is used for production.

**Status: TEMPLATE / P2 PREPARATION. P3 NOT RUN. SCIENCE_HOLD.**

## Temporary metadata and deprecation policy

The `provenance.archive_layer` / `alternate_archive_layer` objects in these
reaction JSONs are **temporary audit metadata**. They are retained while the
S6 scientific source/parity verification is open and are slated for removal
once the external provenance record is pinned. They are not needed at runtime.
The JSON `progress` field, unlike provenance, has already been **removed**;
rate Functor names are generated deterministically by the C++ ID rule.

## Canonical naming rule for new runs

All newly generated model inputs, Functor/BC bindings, diagnostics and
Exodus-facing readers use `log_e_energy`. The only occurrences of the
historical name remain in the guarded archive-to-scratch canonicalization
contract and in provenance/tests verifying old immutable evidence; the run
itself contains only canonical state and progress Functor names. Historical
input archives and previous solver output are **not** rewritten.
