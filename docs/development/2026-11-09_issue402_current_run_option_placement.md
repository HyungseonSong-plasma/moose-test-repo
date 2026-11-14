# Issue #402 — current native-run input option placement / no-loss migration gate

> **User approval (2026-11-09):** Detailed G0 Plasma DSL design approved,
> with an **additional final acceptance requirement**: all options actually
> used by current successful native runs must be correctly placed in the
> new input hierarchy or deliberately retained in native MOOSE scopes.
> **G0_DESIGN_APPROVED / INPUT_PLACEMENT_CONTRACT_APPROVED /
> FULL_PER_OPTION_MAPPING_PENDING / G1_NOT_AUTHORIZED / SCIENCE_HOLD.**
>
> This is a **design and provenance audit**, not a migrated executable input.
> Existing S4–S6 inputs, immutable run artifacts, Physics source SHA,
> MOOSE plugin registrations and original scientific controls are unchanged.

## 1. Scope: distinguish per-case chemistry from common runtime options

Audited actual successful archived input files from **four Native 400 W,
0–100 us / 460-step runs** (Issue477). Each archived artifact includes
the C0 Chemistry-OFF input, RF MultiApp parent overlay, channel-specific
overlays, manifest, runtime log and generated Exodus/CSV. These are
**effective source layers**, not a single parsed/effective normalized HIT;
the final include precedence and dynamic expressions require a later
native assembled-input audit.

| Historical case | Native archive artifact | Input layers | Explicit key=value entries in archived .i files | Chemistry channels |
|---|---:|---:|---:|---|
| S5-417-407 | 13641179390 | 8 | 1,998 | EI-02, EI-17, EI-415, EI-401, EI-417, EI-407 |
| S5-941-407 | 13643402717 | 8 | 2,000 | EI-02, EI-17, EI-415, EI-401, EI-941, EI-407 |
| S6-417-407-2069-H25 | 13677089020 | 10 | 2,171 | EI-02, EI-17, EI-415, EI-401, EI-417, EI-407, EI-2069, H25 |
| S6-941-407-2069-H25 | 13677375813 | 10 | 2,173 | EI-02, EI-17, EI-415, EI-401, EI-941, EI-407, EI-2069, H25 |

**8,342 recorded explicit option instances in total.** Counts refer to
every physically present \`key = value\` line, including repeated common
layers across cases, not 8,342 distinct semantic parameters. The archive
content does not publish the private EI reaction-rate bytes; only their
provenance/declared paths and SHA-256 digests are preserved.

- S5 reference: [completed Run #42521896067](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42521896067).
- S6 reference: [completed Run #42589883028](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42589883028).
- Pinned Physics base source \`29d1acc6ef7969908b86719e4b95c73a1565136d\`.
- MOOSE version \`9f388366ccf38b9c34542ec5561198249fde0ac9\`.
- This list is a representative **S5/S6 400 W starting baseline**; broader
  currently used C0–S6 branches and 1000 W/300 us variants need an
  authoritative per-run census before **G4** migration. Do not infer they
  share identical input option sets.

## 1.1 Updated S6 species mapping — approved user-facing notation

The user removed the unnecessary `schema_version = 1` input parameter and
requested explicit `fem_species` / `fvm_species` classification for each
species-bearing equation. This **replaces** the former generic `species`
option. There is no global `Transport/discretization` switch because
the actual successful run mixes FEM and FV.

```ini
# Conceptual approved design target; NOT a registered MOOSE input.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e'
          fvm_species = 'O2p Om Op'
          fem_charge_numbers = '-1'
          fvm_charge_numbers = '1 -1 1'
          # variable and kernel names derived internally
          # mobility/diffusivity must bind all activated species
        []
        [Energy]
          fem_species = 'e'
          variable = log_energy
        []
      []
      [NavierStokes]
        [Continuity]
          fvm_species = 'O2 O2s O Os'
          # one shared FV mixture mass equation: variable p
        []
        [Momentum]
          fvm_species = 'O2 O2s O Os'
          mixture_velocity = 'u v'
          # one shared FV mixture velocity field, NOT four momenta
        []
      []
    []
  []
[]
```

DD Continuity `fem_species` and `fvm_species` are unique and disjoint.
There is **no user-level `variables` or `fem_kernel_names`/`fvm_kernel_names`**:
Physics derives variable names deterministically (`log_n<species_id>` for
log-number states) and kernel names exactly as `<species_id>_transport`.
The current S6 e/O2p/Om/Op variable names are `log_ne/log_ni/log_nm/log_nop`:
those charged-ion names differ from generic name derivation and require an
audited *internal* S6 alias registry until G2 proves consumer compatibility.
Likewise `ne_transport` cannot silently become `e_transport` during the
pinned Issue #493 P3 B/C comparison.

The shared coefficient options `mobility` and `diffusivity` bind in FEM-first,
then FVM order. This four-species illustration requires four verified provider
bindings; a single electron mobility/diffusivity MUST NOT be broadcast to FV
ions. `fem_charge_numbers` and `fvm_charge_numbers` align with their
respective species lists and match catalogue charges. The user has deferred the Material/Functor naming change: bind the new Physics
option `diffusivity = 'electron_diffusion'` to the **existing** provider.
`electron_diffusivity` is a possible later provider rename only. Preserve
original S6 inputs and require separate source/consumer parity proof. Never silently reorder state,
coefficients, charges or reaction sources. Both NS blocks must
declare identical neutral mixture constituents and a single
mixture-velocity owner. Existing explicit neutral mass-fraction equations
`w_O2s,w_O,w_Os` remain native until given a separate owner.

The two S6 reaction variants change **only EI-417 vs EI-941** in the
activated Chemistry manifest. Neither variant introduces a new
`schema_version` or global discretization user option.

## 2. Destination policy: physical meaning vs native MOOSE execution

**The invariant is NOT "put every key under [Physics]."** A new, declarative
\`[Physics]/[Plasmas]\` subtree owns plasma *physics generation*, while the
framework's native execution and observation scopes remain valid and
explicit. Never silently move a native option into an unrelated equation
block.

| Existing layer and examples found in archived runs | Target placement / logical owner | Required preservation rule |
|---|---|---|
| \`[Mesh]\`: \`coord_type = RZ\`, \`rz_coord_axis = Y\`; subdomains and mesh generators | **Retain native \`[Mesh]\`** | Same mesh, axis convention, side sets, element geometry and field regions |
| \`[GlobalParams]\`: \`rhie_chow_user_object\`, \`advected_interp_method\`, \`velocity_interp_method\`, \`two_term_boundary_expansion\` | Retain native or explicit qualified NS shared numerical policy; **not** automatically repurposed | Exact Rhie–Chow and FV interpolation behavior, no defaults inserted |
| \`[Executioner]\`: Transient, implicit Euler, \`solve_type=NEWTON\`, \`end_time=1e-4\`, tolerances, PETSc flags, TimeStepper | **Retain native \`[Executioner]\` / \`[Preconditioning]\`** | Same integrator, time grid, nonlinear/linear solver, tolerances, convergence criteria, scaling |
| \`[Outputs]\`: CSV, Exodus, checkpoint, \`execute_on\` | **Retain native \`[Outputs]\`** | Same reporting/checkpoint names and execution timing |
| \`[MultiApps]\`, \`[Transfers]\`: \`maxwell_t6\`, field transfers, postprocessor transfer, \`SAME_AS_MULTIAPP\` | **Retain native MOOSE MultiApp/Transfer objects** unless separately approved qualified builder | Parent/child path, mapping direction, target AuxVariable, interpolation, stage and coupling order unchanged |
| \`[Controls]/rf_drive_pid_t6\`: \`PIDTransientControl\`, \`target=400\`, drive \`[0.1,3]\`, \`execute_on=TIMESTEP_END\` | **Retain native \`[Controls]\`**, contractually linked to \`Plasmas/Maxwell\` and RF power | PID tuning, feedback sensor, clamp, update stage, raw-vs-scaled power semantics unchanged |
| RF \`Materials/q_rf_raw_t6\`, \`q_rf_scaled_t6\`, conductivity, \`E_real_rf_t6\`/\`E_imag_rf_t6\` | **Logical \`[Physics]/[Plasmas]/[Maxwell]\` owner**, with explicit native generated/retained projections | Preserve phasor convention, conductivity inputs, transfer scaling and **W/m³** power source; reject double owners |
| \`[FunctorMaterials]\` EI lookup objects such as \`PhysicsElectronImpactRateMaterial\` with \`rate_table_file\`, \`mean_energy\`, \`reaction_progress\` | **Split logical ownership:** \`Transport/Coefficient\` provides *rate coefficient*, \`Transport/Chemistry\` owns *reaction progress* | Do not compute the same kinetic rate twice, change the strict table bounds, rename published progress without binding rewrites or change the Avogadro factor |
| Reaction overlays EI-02/EI-17/EI-415/EI-401/EI-417 **or** EI-941/EI-407/EI-2069/H25: progress, stoichiometry, species sources, electron energy losses | **\`Transport/Chemistry\`**, with source consumers in \`DriftDiffusion/Continuity\` and \`DriftDiffusion/Energy\` | Preserve exact activated reaction IDs and exclusive 417-vs-941 selection, table hashes, stoichiometric signs, energy loss units, 8-channel S6 closure; **H25 remains provisional** |
| \`[Variables]\`: electron \`log_ne\`, \`log_energy\`; heavy \`w_*\`, pressure \`p\`; \`[FVKernels]\` transport and \`[Kernels]\` energy | Logical \`DriftDiffusion\` (electron/charged species) and \`NavierStokes\` (neutral mixture), **only when physically corresponding to the existing equation** | Preserve state form/log transforms, original reference scales, electron/molar unit distinction, exact FV/FEM operators; classify each actual equation before replacing |
| \`[FVBCs]\`, \`[BCs]\`, wall/sheath fluxes, charged particle and surface-current boundary law | Typed \`boundary_contract\` of the actual owning DD/NS/Poisson/Maxwell leaf; native object may remain explicitly present | Identical boundary IDs, wall/surface reactions, flux sign/units, surface charge law, geometry and solver stage |
| Electrostatic charge, potential and \`E_dc\` field | **\`[Physics]/[Plasmas]/[Poisson]\` logical owner** in the FEProblem where it is solved; other apps consume typed transfers | No implicit local \`phi\` producer when Poisson is a different MultiApp, no double potential equations or charge-density projection |
| \`[Postprocessors]\`, \`[AuxKernels]\`, \`[AuxVariables]\`, \`[UserObjects]\` (including geometry probes, power/energy diagnostics, PID feedback receiver) | Primarily **retain native reporting/auxiliary scopes**, with typed logical producer references as needed | Preserve all diagnostic names/units, value extraction, timing, export AuxVariables and control feedback dependencies |
| Native file-level \`!include\`, \`[./]\` nesting, \`[../]\` closures, top-level \`rf_scale_t6\`, \`source_enable_t6\`, \`faraday_t6\` | Retain framework input mechanics / root substitution constants, or explicitly declare a typed parameter mapping *after* dependency audit | No lost scalar substitutions, aliases, repeated-object resolution or change in include order |
| Unrelated MOOSE infrastructure \`[Mesh]\`, \`[Functions]\`, \`[ICs]\`, explicit \`Materials\` and general UserObjects not demonstrably generated by an approved new Physics owner | **Keep native until individually mapped and proven equivalent** | Fail closed on unknown ownership; do not drop because a DSL has a vaguely similar name |

### Key distinction: input options vs semantic owners

A C++ object being declared under \`[FunctorMaterials]\` does not mean
every parameter of that object belongs inside a single \`Chemistry\` block.
The currently registered EI owner **combines rate lookup and progress
publication**. The approved DSL separates their logical responsibilities,
but a later G1 implementation can legitimately wrap/reuse the same native
object *without duplicating it*. The generated object graph and AD
derivatives must remain equivalent.

Likewise, \`[NavierStokes]/[Continuity]/species\` and
\`[NavierStokes]/[Momentum]/species\` refer to one shared mixture, NOT a
command to move all existing heavy mass-fraction equations under a single
mixture mass conservation leaf. Each heavy species equation must have a
declared owner or remain native; preserve the qualified single-mixture
momentum implementation.

## 3. Required complete option-ledger schema for every run

The final machine-auditable record must contain **one entry per resolved
effective option**, plus a source trace for all original declarations
(including overridden ones):

\`\`\`json
{
  "run_id": "Issue477/S6-417-407-2069-H25/400W/100us",
  "source": {
    "input_archive_artifact_id": 13677089020,
    "physics_sha": "29d1acc6ef7969908b86719e4b95c73a1565136d",
    "source_file": "<actual archived input file>",
    "section_path": "FunctorMaterials/ei2069_progress",
    "parameter": "rate_table_file",
    "value": "private_rates/EI-2069_O2_a1Delta.txt",
    "source_sha256": "<sha256 of source file>",
    "include_and_override_rank": "<resolved order>"
  },
  "destination": {
    "mode": "DSL_LOGICAL_OWNER_WITH_RETAINED_NATIVE_OBJECT",
    "physics_path": "Physics/Plasmas/Transport/Chemistry",
    "coefficient_provider": "Physics/Plasmas/Transport/Coefficient",
    "field_or_reaction": "EI-2069",
    "physical_unit": "<validated unit>",
    "owner_feproblem": "<resolved FEProblem>",
    "native_type": "PhysicsElectronImpactRateMaterial",
    "generated_object_name": "<resolved name>",
    "timing": "<original execute stage>"
  },
  "parity": {
    "value_equal": "NOT_EVALUATED",
    "action_graph_equal": "NOT_EVALUATED",
    "native_numerical_equal": "NOT_EVALUATED"
  }
}
\`\`\`

\`<...>\` fields are **placeholders**, not claims about resolved options.
The automated inventory extracted archived \`key=value\` declarations from
four Native run ZIPs, but **full include/override resolution, expression
evaluation, material/functor dependencies and native task graph comparison
are still NOT_EVALUATED**.

### No-loss / no-duplication invariant

Define \(S\) as **all effective input option/value assignments**, their
source provenance and implicit dependencies in a pinned original run.
Define \(T\) as the new executable input assignments **plus** explicitly
retained native MOOSE options.

For each member of \(S\), require one explicit disposition in \(T\):
\`MOVED_TO_PHYSICS_DSL\`, \`RETAINED_NATIVE\`,
\`REPLACED_BY_PROVEN_EQUIVALENT_GENERATED_OBJECT\`, or
\`BLOCKED_NEEDS_SEMANTIC_REVIEW\`.

- For each production migration, **zero** entries may remain
  \`BLOCKED_NEEDS_SEMANTIC_REVIEW\`.
- No unpaired deletions, duplicated equation/reaction/field owners, or
  unexpected new default options. The native MOOSE parser must resolve
  values and hierarchy at the exact pinned revision.
- Generated/retained objects must match canonical semantic identity,
  units, fields, boundary paths, nonlinear and transfer execution ordering.
- Input-source checksum/digest, reaction channel activation, private
  table provenance, mesh, geometry, wall conditions, RF power controller,
  timestep/end-time, PETSc knobs, outputs/checkpoints all remain auditable.
- Regression gates: exact \`--check-input\`; native object/task/transfer
  graph; discrete operator and AD Jacobian-sensitive comparisons;
  restart/checkpoint and event timing; 400-W S5/S6 density/Te, charge,
  conservation, RF power, nonlinear convergence and scientific review.
- Historic S4/S5/S6 source commits and artifacts are immutable oracles;
  migration creates **new** traces, not silent overwrites. All scientific
  \`SCIENCE_HOLD\` gates continue independently.

## 4. Incremental migration and expansion beyond the four archives

1. **G0 approved:** own the complete mapping requirement and this logical
   destination table. Existing-run census is partially complete for the
   four representative 400 W S5/S6 archives; final disposition of all
   individually effective options is still pending.
2. **G1 separately authorized:** build a minimal opt-in \`PhysicsBase\`
   slice and a parser/ownership oracle. Do not change any production
   \`.i\` files.
3. **G2:** build a **per-run input resolver** using the exact MOOSE
   \`!include\` order and runtime substitutions; map all options including
   duplicates and generated defaults. Reconcile owner inventories
   and check the native Action graph.
4. **G3:** test equivalent old/new inputs with identical mesh, coefficient
   data, Chemistry branch, RF Controller, nonlinear tolerances and
   restart/staging. Exercise both EI-417 and EI-941 and single-vs-combined
   EI-407/EI-2069/H25 branches.
5. **G4 separately authorized:** iterate the same protocol across
   1000 W / 300 us, other current accepted/active cases and then future
   runs. Reject missing-option mapping. Roll back to original input by
   switching the explicit migration flag; the default remains legacy
   until user approves cutover.

**This requirement is a mandatory release acceptance criterion, not
authorization to implement, migrate existing inputs or claim scientific
equivalence today.**
