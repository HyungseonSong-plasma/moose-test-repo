# Issue #402 — S6 Chemistry run-input preparation (not scientific acceptance)

## What these files are

- `oxygen_s6_common.json`: **7** archived shared reaction channels (EI-02, EI-17,
  EI-415, EI-401, EI-407, EI-2069, H25) and the validated species/charge catalogue.
- `oxygen_s6_417.json`: **one** EI-417 ionization channel, 17.0 eV/event lost.
- `oxygen_s6_941.json`: **one** EI-941 ionization channel, 13.62 eV/event lost.
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
kinetic expressions, units and numerical values are unchanged.
Each reaction declares `units: "mol/(m^3 s)"` and a nonnegative
`energy_loss_eV` magnitude. The Physics Chemistry projector applies
the **single negative sign** when constructing `Q_e_molar_eV` on the
electron-energy RHS; the original signed physical loss is preserved.

- EI-02 and EI-17: source-defined **variable positive elastic loss**
  `delta_epsilon_EI02_eV` / `delta_epsilon_EI17_eV`. No user-defined
  signed-wrapper FunctorMaterial is needed.
- EI-415: 12.06; EI-401: 0; EI-407: 0.977;
  EI-2069: 5.02 eV/event lost.
- EI-417: 17.0 **or** EI-941: 13.62 eV/event lost.
- H25: `model: none` for **electron-energy** exchange. Its unresolved
  ion-neutral energy partition remains under `SCIENCE_HOLD`; do not interpret
  `none` as an accepted complete energy model.

The [DriftDiffusion] Physics generates species-dependent `DDMaterial`
instances from JSON `transport_coefficients` when present. There is no
separate `[FunctorMaterials]` in the S6 Chemistry overlays; original
Native kinetic/rate and ion coefficient producers are still retained.

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

## Exact-head S6-417/941 P2-only run preparation

The **existing CI** already executes `run_public_option_s6_p2.sh` after the
exact-head Native build, which invokes `public_chemistry_s6_p2.py` for both
real 10-layer archived S6 cases with `physics-opt --check-input`.
This is an input-construction gate, not a physics time integration.

For an operator to inspect all **11 prepared input files** instead of deleting
scratch after P2, the new `run_chemistry_s6_p2_only.py` command is available
after the normal public P0 and P1 prerequisite setup:

```bash
cd <issue402-checkout>
# First perform existing P0 public-S6 source/mesh preparation and the
# same-head Native P1 build (native_p1_identity.json is required).
python3 experiments/Issue402_plasma_dsl_g1/run_chemistry_s6_p2_only.py \
  --historical ../historical \
  --expected-head "$(git rev-parse HEAD)" \
  --case both \
  --output /tmp/issue402-chemistry-s6-p2-review
```

The command refuses an existing output directory and preserves
`S6-417/scratch/`, `S6-941/scratch/`, their eleven input files,
the two Native `--check-input` logs, and `readiness.json`.
Only the **existing** public Native rate sources are staged; no private rates
are fetched. It checks the P1 binary SHA before each P2 invocation and
never invokes a solver timestep, the P3 runner or a GitHub workflow.

**Important distinction:** the P2/P3 Chemistry staging mode still reads
`oxygen_s6_common.json` plus `oxygen_s6_{417|941}.json` and retains
the original Native electron/ion transport and original Native Poisson
RHS owner. This prevents accidental activation of the synthetic P2
`e_transport.txt` and duplicate Poisson or coefficient producers. The
`review_s6_*_full.json` files remain **review-only** until validated,
physically qualified transport data and canonical Native coefficient
bindings exist.

For **new** FEM Poisson inputs, `PoissonEq` can explicitly bind
`charge_source_functor = poisson_charge_source` to the
`PhysicsPlasmaChargeDensityMaterial` AD Functor using one
`FunctorKernel` with `functor_on_rhs = true`. It also supports the
older `charge_source_material` FE Material Property, mutually
exclusively. Do not add a `[Poisson]` charge source to an archived
S6 deck that already owns its Poisson equation; the full Native staged
P2 test is the gate for that combination.

**P3 remains NOT_RUN and requires separate explicit operator authorization.
SCIENCE_HOLD and original ten-layer baseline inputs remain unchanged.**

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


## S6-417/941 archived electron transport lookup compatibility (2026-11-13)

The preserved public B/C decks have exactly one original
\`[FunctorMaterials]/[electron_transport]\` in the common base input:
\`PhysicsElectronTransportLookupMaterial\`. Original parameters are exactly
\`property_table_file='../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'\`,
\`mean_energy=mean_en_solved\`, \`pressure=p\`,
\`gas_temperature=T_g_fixed\`, \`bounds_policy=clamp\`, \`block=plasma\`.
The \`clamp\` policy and \`T_g_fixed\` input are **required historical behavior**;
do not silently substitute \`error\` or \`T_g\`.

\`prepare_s6_run_input.py\` now performs a **strict, scratch-only conversion**
after validating the exact owner and all original parameter values. The
disposable D copy becomes \`DDMaterial\` with \`species_id=e\`,
\`model=lookup\`, the *same original* \`table_file\`, \`table_units=reduced\`,
\`pressure=p\`, \`gas_temperature=T_g_fixed\`, \`bounds_policy=clamp\`,
\`fluid_energy=true\`, \`block=plasma\`. No B/C archive file, physical
transport table or kinetic rate provider is rewritten. Any altered original
table path, coordinate, pressure, temperature, bounds policy, duplicate owner
or unknown factory fails closed.

Both historical and new C++ implementations interpolate the same reduced
electron mobility/diffusivity and divide by
\`N_n = p/(k_B*T_g)\` for physical coefficients; electron energy transport
uses \`5/3\` times the particle coefficients. For the accepted positive
pressure/temperature domain, source-level equations match. Their exception
behavior differs for unphysical/invalid transport values and is *not*
claimed equivalent.

**Public-data caveat:** The committed original electron_moments.txt contains
100 rows (Git blob \`bedcaf17fb3ef93ba8973cc6b32aa6e783e2292a\`). The
historical 400 W native preparation *intentionally replaces it* with the pinned
42-row public initial-mixture table (Git blob
\`aa05aadde111e4ba435185954a64a4b7dbbf2d45\`) in the scratch
historical checkout. Validation checks **both distinct inputs**, table
positivity/ordering and bounded interpolation; neither should be confused
with the review-only synthetic e_transport.txt.

- Original B/C S6-417/941 block identity:
  [P0 source audit #43402376955](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43402376955)
  PASS.
- Source-bound [P0/P1/native P2 #43403730997](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43403730997)
  on \`2c79d2327367aeaa078726af0b3df5c9dc9d4a5f\`:
  **613 P0 PASS**, public 400 W mesh PASS, exact-source Native P1
  PASS. Both full 11-layer S6-417/941 Native P2 still **HOLD at that historical run**.
  The previous first parser error
  \`PhysicsElectronTransportLookupMaterial is not a registered object\`
  has disappeared. The new first parser error in both cases is
  \`PhysicsLowerDSurfaceCurrentProbeAux is not a registered object\`,
  a **separate retired lower-D diagnostic AuxKernel**. Do not restore
  its C++ factory or drop its diagnostic ownership without independent
  verification.
- The exact native log and manifest for this run are in
  [artifact #14026497410](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43403730997/artifacts/14026497410).
  Python formula/fixture parity and Native \`--check-input\` do **not** prove
  numerical temporal parity, actual old/new C++ face-value parity or full
  science acceptance. No P3, no merge; \`SCIENCE_HOLD\` remains.



## Native S6 D base with obsolete D1 debugging absent by construction (2026-11-13)

**Operator scope:** Issue397 D1 diagnostics were temporary instruments for a
resolved defect. Their 9 surface-current probes, 5 geometry probes, and
14 AuxVariables are not required in the target D model. No numerical parity
or independent review of these now-retired outputs is required. Physical
`PhysicsLowerDSurfaceCurrent`, sheath/Wall/RF sources and transport remain.

**Source of truth:** The original public B/C S6-417 and S6-941 archives
remain SHA-pinned and unmodified. Both public C variants share exactly the same
original C0 physics base (`SHA256:
66548d33947b227ca29849b0c52146100887d1795a66e0f90df11a94199fc5bf`).
A **one-time** archival migration produced
`experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i`
(`SHA256:
c9686adb669cc115556860c00438fcfdd93a438751e9f99825b4ddb6ebf65088`).
Generation was source-bound, verified exactly 14 debug AuxKernels and 14 paired
AuxVariables were removed, and confirmed physical owners were preserved.
[One-time generation evidence #43419992876](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43419992876).

**Production input creation:** All four known D input entrypoints now use
`public_p2_check.stage(..., d_base_source=.../native/s6_c0_physics_base_no_d1.i)`:
`run_chemistry_s6_p2_only.py`, `public_chemistry_s6_p2.py`,
`public_option_s6_p2.py` (D arm only) and
`run_canonical_s6_p3_once.py` (future, separately authorized P3).
The staged D base therefore **never contains** the obsolete debug Aux objects.
Historical B/C `stage()` with no override retains its original byte-identical
deck. The historical `issue397_d1_instrument.py` is a provenance-only
generator; the active D path never invokes it.

The former `suspend_staged_retired_d1_observations()`, its 14-entry maps,
`audit_final_native_d1_debug_absence()`, recurring pre/post-write scans and
their dedicated negative-control tests have **all been deleted**. The active
input is not created with diagnostics and then stripped; no per-run D1
cleanup or absence scan is executed. A compact P0 source SHA pin and direct
staging regression cover fixture integrity and B/C non-interference without
rebuilding the obsolete debug analysis.

**Historical transition evidence:** Prior active-input run
[#43418084078](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43418084078)
passed P0 641, Native P1, and Native S6-417/941 P2 using temporary filtering
and scanning. That was a transitional implementation and has been superseded
by the direct-source construction above; it must **not** be cited as proof
that the final refactored path ran until its own exact-source CI completes.

**Remaining science gates:** Native `--check-input` is an input-validity
check, not a numerical time-integration, face-value parity or scientific
mechanism-provenance check. `SCIENCE_HOLD` stays active; P3/P4 remain
`NOT_RUN`, PR #524 remains Draft stacked onto PR #523, and no merge is
authorized by the D1 cleanup alone.

**Final direct-source verification**: [Actions #43421515139](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43421515139), exact implementation SHA `0fd8a97bf5cf720eb0625b20aa9160a7fcb0efe8`: **623 P0 PASS**, public mesh PASS, source-bound Native P1 PASS, and **S6-417 plus S6-941 active Native P2 both PASS (`Syntax OK`, exit 0)**. [Immutable logs/receipts #14034922005](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43421515139/artifacts/14034922005). Every D entrypoint uses the pinned prebuilt source; the per-run D1 strip and scan stages do not exist. One-shot CI files are subsequently removed, without modifying tested implementation. `SCIENCE_HOLD`, no P3/P4 and no merge.
