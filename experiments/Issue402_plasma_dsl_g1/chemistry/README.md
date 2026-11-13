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
  PASS. Both full 11-layer S6-417/941 Native P2 still **HOLD**.
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



## S6-417/941 retired D1 Aux diagnostic compatibility gate (2026-11-13)

**Source audit, immutable B/C:** The 11-layer S6-417/941 public archive
contains 9 `PhysicsLowerDSurfaceCurrentProbeAux` face-Functor observers,
5 `PhysicsWaferD1GeometryProbeAux` observers, and 14 corresponding
`wafer_surface` MONOMIAL AuxVariables in the shared base layer. Every
observed variable has exactly two token references across the archived
input stack (its declaration and its own diagnostic AuxKernel). No
physics/RF/PDE residual, boundary condition or producer consumes those
14 AuxVariable names in the pinned deck. See [immutable B/C audit
#43405429511](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43405429511).

Both historical C++ AuxKernel implementations existed at historical
`29d1acc6ef7969908b86719e4b95c73a1565136d` but are no longer
registered in the current PhysicsApp. They sampled the plasma-side
`FaceArg` / signed face current and geometry (`normal_r`, `normal_z`,
`owner`, `d_perp`, `e_n`). The currently registered physical kernel
`PhysicsLowerDSurfaceCurrent` is a distinct PDE residual owner and
**must not** be removed or treated as a diagnostic substitute.

**Bounded disposable D core-input P2:** The staging helper
`suspend_staged_retired_d1_observations()` verifies all 14 paired
signature/owner/section assignments, rejects duplicate, missing,
externally consumed or unexpectedly indented parameters, and removes
only the 14 diagnostic AuxKernels and 14 associated AuxVariables
from temporary D scratch. Physical Wall current Functors, surface-charge
residuals, Poisson/transport/RF source owners and original B/C inputs
are kept intact. Because diagnostics are omitted, this input is
**CORE_INPUT_P2_ONLY**, never full original S6 acceptance.

**Exact-source P0/P1/P2 evidence**: [run #43407079646]
(https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43407079646)
on tested SHA `e63791f10c54c8fa2d4c20a1c3cd549b9b07c1a7`:
- P0 **638 tests PASS**, including the fixed 42-row public staging table
  and deliberately invalid B/C owner/consumer/hidden-assignment inputs.
- Public 400 W mesh prepared, exact-source Native P1 compiled **PASS**.
- Real 11-layer S6-417 core-input `physics-opt --check-input`: **Syntax OK**, exit 0.
- Real 11-layer S6-941 core-input `physics-opt --check-input`: **Syntax OK**, exit 0.
- [Run artifact #14027838281]
  (https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43407079646/artifacts/14027838281)
  contains exact case-local logs, SHA-based source binding and bounded P2 receipts.

The earlier missing `PhysicsLowerDSurfaceCurrentProbeAux` and
`PhysicsWaferD1GeometryProbeAux` no longer block this **core** syntax test.
That is **not** C++ face-value regression, observational equivalence,
temporal/physics parity or validation of the missing 14 diagnostics.
**Historical gate as initially defined:** the initial experimental run marked
`FULL_S6_P2=HOLD` and `DIAGNOSTIC_PARITY=HOLD`; CodeRabbit's D1 follow-up
review was rate-limited. These historical facts remain in the immutable run
artifact. The later operator decision below supersedes the *requirement* to
reproduce/debug-review the retired D1 probes, but does not change that
historical report.


## Operator decision: D1 debugging complete; diagnostic retirement accepted (2026-11-13)

The operator confirmed that the original Issue397 D1 instrumentation was
introduced solely to investigate a specific defect, and that defect has
already been identified. The D1 probes are no longer required model outputs.
Consequently, **recreating 14 retired probe values / FaceArgs, proving
diagnostic numerical parity, and arranging a separate independent reviewer
for this now-unneeded instrumentation are not acceptance gates**. This is an
explicit operator scope decision, **not** a claim that those values were
reproduced or that a reviewer approved the retired code.

The active target S6 D input excludes precisely 9 retired
`PhysicsLowerDSurfaceCurrentProbeAux` and 5
`PhysicsWaferD1GeometryProbeAux` instances plus their 14 unused AuxVariables.
The guarded scratch-only transformation checks the exact archival signatures
and ensures no unexpected variable consumer before removing them. The
original B/C archive stays byte-identical and auditable, not rewritten.
All physical `PhysicsLowerDSurfaceCurrent`, Wall, Poisson, transport,
RF and Chemistry owners remain part of the active target.

**Active model Native P2 acceptance** means `physics-opt --check-input`
succeeds for the S6-417 and S6-941 stacks *after the explicitly retired
debug probes are removed*. The last source-bound evidence already showed
both cases `Syntax OK` in [run #43407079646](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43407079646).
Historical evidence called this `CORE_INPUT_P2=PASS`, because the old
diagnostic parity gate was still pending; this operator decision now
makes that the **intended target model input**, not a temporary missing
science component. Current staging records
`OBSOLETE_D1_DEBUG_OBSERVATIONS_RETIRED`,
`diagnostic_parity=NOT_APPLICABLE`, and
`d1_retirement_review=NOT_REQUIRED_OPERATOR_DECISION`.
The active P2 runner verifies exactly 14+14 removals before accepting Native
syntax. Do not rewrite or reclassify historical signed CI receipts.

**Remaining distinct gates:** Native C++ wall/transport physical parity and
scientific provenance/trajectory acceptance are not proven by `--check-input`.
`SCIENCE_HOLD` stays in effect; P3/P4 remain `NOT_RUN`, and neither
PR #524 nor the stacked parent PR #523 is merged. This decision waives
only *D1 debug-specific* reproduction and optional independent D1 review,
not repository protection rules or evidence required for actual physics
compatibility.


### Exact-source active S6 Native P2 result after D1 retirement

[Workflow run #43416474682](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43416474682)
at source SHA `44b2ba1c2784ae33e5adad6388b5cd4783de7f24`
completed successfully using the operator-approved active input definition:
**638 P0 tests PASS**, pinned public mesh P0 PASS, source-bound
PhysicsApp Native P1 PASS, S6-417 and S6-941 Native P2 **both
`Syntax OK` / exit 0**. The output contract records
`ACTIVE_MODEL_P2=PASS`, `RETIRED_D1_PARITY=NOT_APPLICABLE`,
`RETIRED_D1_REVIEW=NOT_REQUIRED_OPERATOR_DECISION`, and
`SCIENCE_HOLD`, with P3 `NOT_RUN`.
[Artifact #14033140207](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43416474682/artifacts/14033140207)
preserves the case-local native input logs and bounded source identity
receipts. This replaces the *current* D1-related P2 hold classification
without changing any archived old run or science-gate decision.


## Verified final Native S6 .i files without retired D1 Aux (2026-11-13)

The active S6 target D input builder now checks the complete **11-layer
Native .i stack** both in-memory (before any cutover files are written) and
again from the **files actually written to disk**. The Native P2 runner
independently re-reads those exact 11 files immediately before invoking
`physics-opt --check-input`. Any occurrence of the 14 named obsolete D1
AuxVariables, their 14 AuxKernel blocks, or either retired AuxKernel factory
type causes a fail-closed error. This is an *actual target-input exclusion*,
not simply ignoring their results or relaxing assertions. Original B/C
archive evidence stays unchanged. The obsolete diagnostic numerical-parity
and standalone D1 retirement review gates are **not applicable** by the
operator's decision; physical numerical equivalence remains a separate gate.

[Exact-source native run #43418084078](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43418084078)
(HEAD `813da8b267a24487274f7c96a2ce3cf4f0443af8`): **641 P0 tests PASS**;
public 400 W mesh PASS; source-bound Native P1 PASS;
**S6-417 and S6-941 Native P2 both PASS, exit 0, Syntax OK**;
all 11 layers explicitly audited zero obsolete D1 diagnostics.
[Artifacts #14032148589](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43418084078/artifacts/14032148589).
P3/P4 remain NOT_RUN, independent physics/Wall numerical parity unproven,
`SCIENCE_HOLD` maintained and no branch merge authorized.
