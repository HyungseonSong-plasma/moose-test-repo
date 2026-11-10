# Issue #402 — G0 Plasma Physics DSL detailed contract (review draft)

> **Authority / status:** The user approved D1–D8 and subsequently approved this G0
> detailed design on 2026-11-09 in [Issue #402](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/402).
> **G0_DESIGN_APPROVED; G1_IMPLEMENTATION_NOT_AUTHORIZED; SCIENCE_HOLD.**
> Parameter names, ownership rules and validation policies below constitute the approved
> **design target**, NOT an already implemented or Native-validated executable schema.
> Exact C++ class composition, source-interface support and numerical equivalence remain
> subject to separately approved G1–G4 verification.

## 0. Baseline, boundaries and non-goals

- Immutable dependency lock: \`physics_app/dependencies.lock\`, MOOSE
  \`9f388366ccf38b9c34542ec5561198249fde0ac9\`, build base
  \`ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008\`.
- This MOOSE revision has \`PhysicsBase\`, \`registerPhysicsBaseTasks\`,
  \`registerSyntax\` and e.g. \`Physics/NavierStokes/Flow/*\` registration.
  It **does not establish** that \`Physics/Plasmas/*\` is already registered
  by PhysicsApp. Current \`PhysicsApp.C\` registers \`PlasmaClosures/*\` and
  \`GummelIteration/*\` (plus the installed modules).
- Reference consumers: existing \`physics_app/docs/plasma_closures_action.md\`,
  \`physics_app/docs/gummel_iteration_action.md\`, and the pinned graded-L1
  400-W / 100-us S5-417-407 case. The Maxwell scalar-harmonic
  \`Issue202/rf_power.i\` is characterization evidence, not a generic API.
- Scope: **PhysicsApp-specific MOOSE input DSL and exact local equation/field
  ownership**. This is *not* a SOL canonical type change, adapter HIT
  implementation, chemistry-kinetics redesign, solver upgrade, scientific
  approval, physics parameter change, or migration permission.
- The previously agreed block hierarchy is preserved verbatim. Any design
  metadata below is a proposed parameter inside those existing blocks, **not**
  a new sibling or a renamed \`Transport\`, \`Poisson\`, \`Maxwell\` block.
- The native parser, ABI and \`--check-input\` for this proposed syntax remain
  **NOT_EVALUATED** until a separately approved implementation runs.

## 1. Hierarchy, cardinality and activation (D1–D2)

\`\`\`text
[Physics]
  [Plasmas]                        # 0..1 per FEProblem input
    [Transport]                     # 0..1
      [Coefficient]                 # 0..1
      [Chemistry]                   # 0..1
      [DriftDiffusion]              # 0..1
        [Continuity]                # 0..1, species vector
        [Energy]                    # 0..1, electron only in v0.1
      []
      [NavierStokes]                # 0..1
        [Continuity]                # 0..1, single mixture-mass equation
        [Momentum]                  # 0..1, shared mixture velocity/momentum
      []
    []
    [Poisson]                       # 0..1
    [Maxwell]                       # 0..1
  []
[]
\`\`\`

- **No repeated, anonymous, or wildcard \`Plasmas\` children** in v0.1.
  An inactive/absent child generates **no** objects; groups alone generate
  none. An executable \`Plasmas\` input must activate at least one concrete
  equation owner. Per-child \`active\` is *not* invented; omission is the
  proposed disable operation. MOOSE's general \`active/inactive\` handling
  must be checked at the pinned revision before permitting it in this DSL.
- Singleton scope is **the local FEProblem**, not the overall multi-app tree.
  E.g. \`OUTER_MAIN\`, \`SUB_ELECTRON\`, \`SUB_POISSON\` may each have a distinct
  \`Plasmas\` group and disjoint solved fields.
- Each generated object has the canonical identity
  \`(application instance, FEProblem, kind, name, variable/region)\`.
  Names must not collide with any explicit legacy MOOSE object or existing
  native \`Physics/NavierStokes/Flow/*\` owner. A repeated source of the
  **same equation/field** is invalid even when object instance names differ.
- No mixing of implicit default densities, timestep policy, BC, discretization,
  solver settings or RF power controllers. Explicit physical and numerical
  bindings are required for an executable leaf.

## 2. Shared metadata and vocabulary

These names are the **approved G0 design targets**, not existing C++ parameter registrations.
Implementation must verify exact native compatibility; any mismatch requires a bounded design amendment instead of silent renaming.

**2026-11-09 user-directed amendment:** Do not require input-level \`schema_version\`.
The pinned PhysicsApp/MOOSE implementation defines registered input semantics;
external catalogue formats may carry independent version metadata.
Do not add an implicit schema-version field or reject an input for omitting it.

**2026-11-10 user-directed Continuity refinement:** The Continuity input does not accept `variables` or `fem_kernel_names`/`fvm_kernel_names`. Physics derives state-variable names from canonical species IDs and state form. The default log-number naming rule is `log_n<species_id>` (so `e -> log_ne`). An audited internal compatibility registry, not user-level variable options, must preserve archived S6 `O2p -> log_ni`, `Om -> log_nm`, `Op -> log_nop` bindings until equivalence is established. Generated Continuity kernels are named exactly `<species_id>_transport` (e.g. `e_transport`), independently of `name_prefix`. Duplicate physical-equation owners are rejected even when names differ. **This is a design target, not the currently pinned PR #491 or Issue #493 P3 runtime input.**

**Discretization is local to the equation/species, never a global
\`Transport/discretization\` switch.** Species-bearing equation leaves use
\`fem_species\` and \`fvm_species\`. Both must contain unique, known,
mutually disjoint species, and each selected numerical implementation must
be present in the pinned app. An omitted list means no species in that
numerical family, not an automatic equation.

| Path | Proposed parameter : type | Required / default | Validation/meaning |
|---|---|---|---|
| \`Transport\` | \`species_catalog: FileName\` | required **when any transport/chemistry child is active** | Versioned catalogue with stable IDs and mass/charge states; file digest recorded. No inferred species. |
| \`Transport\` | \`region: vector<SubdomainName>\` | required for equation-generating transport leaves | Explicit mesh block restrictions, no silent \`all\`. |
| \`Poisson\`, \`Maxwell\` | \`region: vector<SubdomainName>\` | required if active | Can differ from Transport, with explicit cross-region field coupling. |
| All equation leaves | \`owner_mode: enum {generate,external}\` | **required** | \`generate\`: own variables/kernels/sources; \`external\`: consume separately owned state only and create **no duplicate equation**. Validation still checks provider and consumer bindings. |
| All equation leaves | \`boundary_contract: FileName\` | required for \`generate\` | Explicit supported BC, boundary IDs and units; no automatically invented wall/flux treatment. |
| All leaves | \`name_prefix: string\` | required | Deterministic object naming scoped by FEProblem. Prefix does not waive semantic conflict detection. |

**Species catalogue proposal (versioned file, not new \`[Species]\` syntax):**

\`\`\`json
{
  "schema": "physics.plasma_species_v1",
  "species": [
    {"id": "e", "phase": "electron", "charge_number": -1, "molar_mass_kg_mol": 0.000548579909065},
    {"id": "O2", "phase": "neutral", "charge_number": 0, "molar_mass_kg_mol": 0.032},
    {"id": "O", "phase": "neutral", "charge_number": 0, "molar_mass_kg_mol": 0.016},
    {"id": "O2p", "phase": "ion", "charge_number": 1, "molar_mass_kg_mol": 0.032}
  ]
}
\`\`\`

This is an **illustrative partial catalogue**: numeric masses and identifiers
are candidate fixtures, not a claim about the actual Oxygen14 mechanism.
Complete simulation catalogues must contain **all** activated species and
their accepted values. Reject duplicate IDs, non-finite/nonpositive masses,
inconsistent charge/phase, unknown referenced species and ambiguous aliases.
Species order in lists is preserved for mappings, but canonical membership
comparison is order-insensitive. The catalogue is local to each FEProblem;
cross-app species identity and units must be explicitly validated.

**Binding policy:** Every named input functor, variable, coefficient, rate,
potential, field and energy source is typed by
\`{name, kind, SI_unit, owner_app, FEProblem, region, producer|external, time_stage}\`.
A string with the right name but the wrong units or source scope is not valid.

## 3. Per-leaf parameter and equation contract (proposed)

### 3.1 \`Transport/Coefficient\` — *coefficient provider*, never PETSc solver

| Parameter | Type | Requirement and meaning |
|---|---|---|
| \`solver\` | \`MooseEnum(Boltzmann MonteCarlo)\` | **required**, preserves agreed spelling; selects coefficient provider only. |
| \`source_mode\` | \`MooseEnum(verified_table on_demand)\` | **required**; \`on_demand\` rejected until a native provider capability is verified. |
| \`source_file\`, \`source_sha256\` | \`FileName\`, hex digest | Required for \`verified_table\`; manifest and bytes checked at construction. |
| \`mean_energy\` | \`MooseFunctorName\` | Required; documented coordinate unit **eV** (not electron temperature K). |
| \`out_of_range\` | \`MooseEnum(error)\` | Fixed \`error\` in v0.1: no clamp, floor, unapproved extrapolation or automatic provider fallback. |
| \`outputs\` | named coefficient interface manifest | Required; typed list: mobility, diffusion, electron-impact rate coefficients with quantity, unit, species/reaction ID and table domain. |

- **Boltzmann** and **MonteCarlo** are selectable *contract identities*, not
  evidence of executable solver support. \`verified_table\` may be accepted
  only when provenance and units prove its declared generating method.
  A request for an unimplemented \`on_demand\` provider is **UNSUPPORTED**.
- Electron-impact \`k_raw\` table dimension must be explicitly distinguished
  from a number-density coefficient; do not silently change the Avogadro
  factor in \`ElectronImpactRateMaterial\`. E.g. legacy
  \`k_raw [m^3/(mol s)]\`, \`n_e [1/m^3]\`, \`c_target [mol/m^3]\` gives
  molar reaction progress via \`R = k_raw*(n_e/N_A)*c_target\`.
- This provider does **not** create a chemistry progress owner, species
  continuity equation, \`LinearSolver\` or \`Executioner\` configuration.

### 3.2 \`Transport/Chemistry\`

| Parameter | Type | Requirement and meaning |
|---|---|---|
| \`mechanism_file\`, \`mechanism_sha256\` | \`FileName\`, digest | Required; ordered, versioned reactions and stoichiometry. |
| \`reaction_ids\` | \`vector<string>\` | Required, unique, subset of mechanism; no default activation of all reactions. |
| \`coefficient_provider\` | typed provider reference | Required for electron-impact reactions unless a separately verified non-electron rate owner exists. |
| \`progress_prefix\` | \`string\` | Required; exactly one progress functor \`R_<reaction_id>\` per activated reaction. |
| \`electron_energy_loss_policy\` | \`enum(explicit_per_reaction)\` | Required where electron-energy loss exists; each loss value specified with **eV/reaction** and converted consistently. |
| \`conservation_policy\` | \`enum(strict)\` | Required; conservation audit of mass, charge and energy-projection consistency. |

Mechanism identity, molar species source projection and energy-loss projection
are **Chemistry-owned**. Rate coefficient interpolation is
**Coefficient-owned**. A reaction source may be consumed by multiple
equations but must be computed **once**. Missing species/stoichiometry, loss
terms, or conflicting rate owners fail closed. H25 provisional physics is
never auto-enabled.

### 3.3 \`Transport/DriftDiffusion/Continuity\`

| Parameter | Type | Requirement and meaning |
|---|---|---|
| \`fem_species\`, \`fvm_species\` | \`vector<string>\` each | At least one nonempty, disjoint, unique; each species known in catalogue and supported by its chosen FEM/FV charged-transport model. |
| Derived Continuity state variables (no user-facing `variables`) | internal naming policy + verified species registry | Deterministically generate names using species ID and state representation. Default log-number form: `log_n<species_id>` (e.g. `e` → `log_ne`). Historical S6 aliases `O2p/Om/Op → log_ni/log_nm/log_nop` require audited internal compatibility mapping before new naming can replace them. Preserve state transformation, units, reference scale and physical ownership. |
| \`electric_field\` | typed field reference | Required for drift-active species; may be external Poisson field; never created twice. |
| `mobility`, `diffusivity` | `vector<MooseFunctorName>` (shared FEM/FVM option keys) | Required 1:1 with activated FEM then FVM species, units **m²/(V s)** and **m²/s**. Do not silently broadcast a single electron coefficient to several FV ions. `electron_diffusivity` is a possible later provider rename but is **out of scope** for the option-first implementation. Keep native `electron_diffusion` production and consumers unchanged and bind it through the new `diffusivity` option. |
| `fem_charge_numbers`, `fvm_charge_numbers` | `vector<int>` each | Required for each nonempty discretization list; numbers align with that list's species, and must agree with the signed charge recorded in the species registry. S6: FEM `-1`, FVM `1 -1 1`. |
| Generated Continuity kernels (no `fem_kernel_names` or `fvm_kernel_names` option) | internal naming | Each activated species gets precisely `<canonical_species_id>_transport` (e.g. `e_transport`); collision-check against legacy `ne_transport` by variable and physical equation, not just name. |
| \`reaction_sources\` | \`vector<MooseFunctorName>\` | Required 1:1 in FEM-then-FV species order; explicit zero permitted and number/molar conversion preserved. |
| \`owner_mode\`, \`boundary_contract\` | shared | Required; one species continuity residual per species for \`generate\`. |

No hidden electroneutrality, sheath, ambipolar boundary rule, charged-state
normalization or diffusion-clamp changes. A neutral species may not
accidentally acquire charged drift terms merely from its membership.

### 3.4 \`Transport/DriftDiffusion/Energy\`

| Parameter | Type | Requirement and meaning |
|---|---|---|
| \`fem_species\`, \`fvm_species\` | \`vector<string>\` each | Exactly one list must contain \`e\`; the other absent/empty. Current S6 electron energy is FEM (\`fem_species = 'e'\`); FV energy requires separately verified Native support. |
| \`variable\`, \`state_form\`, \`reference_scale\` | \`VariableName\`, enum, positive Real with unit | Required; distinguish solved electron energy density from \`T_e\` or mean-energy functors. |
| \`electron_density\`, \`mean_energy\` | typed functor refs | Required; explicit density and eV mean-energy convention. |
| \`energy_mobility\`, \`energy_diffusion\` | typed functor refs | Required; explicitly documented coefficient units and electron-energy transport closure. |
| \`joule_heating\`, \`reaction_energy_loss\` | typed functor refs | Required; positive/negative sign, volumetric rate unit and owner. |
| \`owner_mode\`, \`boundary_contract\` | shared | Required. |

No assumed factor \`3/2\` or hidden \`T_e\` conversion; any electron mean energy
to temperature mapping is an explicitly named material/functor contract with
units. Do not silently substitute the existing \`log_energy\` variable for
physical \`eV/m³\` without the pinned source's state transformation.

### 3.5 \`Transport/NavierStokes/Continuity\` and \`Momentum\`

| Path | Parameter | Requirement and meaning |
|---|---|---|
| Both | \`fem_species\`, \`fvm_species: vector<string>\` | Required unique/disjoint neutral-mixture constituents. Lists match in both NS blocks. S6 uses \`fvm_species = 'O2 O2s O Os'\`, denoting one FV mixture, **not per-species momentum**. Both numerical families must not generate the same mixture. |
| Both | \`mixture_density: MooseFunctorName\` | Explicit **kg/m³** state/owner; one mixture identity. |
| Both | \`mixture_velocity: vector<VariableName>\` | Single shared velocity field, with mesh-dimension-compatible components. |
| Continuity | \`density_variable: VariableName\` | Exactly one mixture mass-continuity residual when \`generate\`. |
| Momentum | \`pressure: MooseFunctorName\`, \`viscosity: MooseFunctorName\` | Required, respectively **Pa**, **Pa s**; explicit source/BC/viscous closure. |
| Both | \`composition: vector<MooseFunctorName>\` | Required 1:1 in declared FEM-then-FV mixture constituent order, with dimensionless mass fractions and sum-to-one validation. |
| Both | \`owner_mode\`, \`boundary_contract\` | Required; forbid repeated momentum generation by dimension/species loops. |

The paired blocks must use one composition and one mixture density/velocity
owner. The two species lists describe *mixture constituents* and the
discretization of the single mixture equation; never per-species mass or
momentum equations. If only one of \`Continuity\` or \`Momentum\` is present, it must
**explicitly** consume the other equation's external state and pass validation;
no implicit second equation is created. An existing
\`Physics/NavierStokes/Flow/*\` owner for the same mixture variables is a
collision. Neutral species composition equations are **not** generated by
these mixture equations; dedicated composition transport needs a later
independently approved contract.

### 3.6 \`Poisson\`

| Parameter | Type | Requirement and meaning |
|---|---|---|
| \`potential_variable\` | \`VariableName\` | Required, single solved \`phi\` owner per FEProblem for \`generate\`; **V**. |
| \`charge_density\` | typed functor ref | Required, **C/m³**, includes electron and charged heavy sources explicitly. |
| \`permittivity\` | typed functor ref | Required, **F/m**; region/material/boundary behavior explicit. |
| \`electric_field_output\` | typed functor name | Required, **V/m**, derived from \`phi\` with explicit sign and producer. |
| \`owner_mode\`, \`boundary_contract\` | shared | Required; prohibit competing explicit Poisson kernels/BCs. |

The Poisson FEProblem may be a dedicated Gummel subapplication; consumers
in another app use transferred **AuxVariables**, not a hidden shared nonlinear
variable. Electron response and sheath policies are **not** auto-enabled.

### 3.7 \`Maxwell\`

| Parameter | Type | Requirement and meaning |
|---|---|---|
| \`field_real\`, \`field_imag\` | \`VariableName\` | Required paired RF unknowns, explicit electromagnetic representation. |
| \`frequency_hz\` | positive Real | Required, **Hz**, not angular frequency; conversion recorded. |
| \`conductivity_real\`, \`conductivity_imag\` | typed functor refs | Required, **S/m**. |
| \`rf_power_output\` | typed functor name | Required, **W/m³** with one owner. |
| \`source_contract\`, \`boundary_contract\` | \`FileName\` | Required explicit coils/current phase, EM boundary and subdomain semantics. |
| \`phasor_convention\` | enum | Required e.g. \`peak_exp_positive_iwt\`, no implicit RMS conversion. |
| \`owner_mode\` | shared | Required; forbid duplicate RF field or power deposition. |

The existing Issue202 reference uses peak phasors and
\`Q_RF = 0.5*sigma_R*|E_hat|²\`; this is a **characterization anchor**
for a later, explicitly qualified axisymmetric RF model, not a blanket
Maxwell API acceptance. Maxwell fields must not be rebuilt from a generic
\`Poisson/electric_field_output\` unless an exact valid coupling is declared.

## 4. Field, state and equation ownership matrix

Each row names a **logical owner**, not a newly implemented class. The
machine-readable companion
\`2026-11-09_issue402_g0_ownership_matrix.json\` carries the same contract.

| Resource / quantity | Sole owner in a generating FEProblem | Permitted consumers | SI unit / safeguard |
|---|---|---|---|
| charged species densities and balances | DD/Continuity for each activated species | Chemistry, DD/Energy, Poisson via local source or external typed transfer | number or molar concentration **as explicitly declared**; no silent \`N_A\` conversion |
| electron energy equation / mean energy | DD/Energy equation; closure defines derived functor | coefficient provider, Chemistry, transport | energy-density **eV/m³** or documented normalized state; mean energy **eV** |
| electron-impact rate coefficients | Coefficient provider | Chemistry progress functor | declared raw unit, e.g. **m³/(mol s)** |
| reaction progress & stoichiometric projections | Chemistry | DD, NS composition where later supported, energy | **mol/(m³ s)** and explicitly converted projections |
| mixture mass continuity | NS/Continuity | NS/Momentum, other local consumers | **kg/(m³ s)** residual |
| mixture velocity and momentum | NS/Momentum | NS/Continuity, advection, transfer | **m/s** shared field, 1 vector per FEProblem |
| Poisson potential, charge and DC field | Poisson (charge closure consumed from Chemistry/species) | DD drift, electron closure, Transfer | **V**, **C/m³**, **V/m** |
| RF complex field and RF absorbed power | Maxwell | DD/Energy/Joule, RF PID read-only | documented field representation and **W/m³** |
| Gummel parent/child transfer and convergence | existing \`GummelIterationAction\` in driver | sub-Electron/Sub-Poisson | explicit AuxVariable sinks and stage timing |
| outer frozen heavy snapshot | \`OUTER_MAIN\` heavy owner | \`GUMMEL_DRIVER\`, subapps (read-only during inner iterations) | no inner heavy advance |

**Important distinction:** A chemistry reaction progress is a single producer
in one application, while its source projection may be a *consumer* in multiple
equations. That is not an ownership conflict. Re-creating identical progress
functors in two distinct FEProblems is permitted only if each uses the
correct, locally scoped data and the cross-app meaning is explicit.

## 5. Native Action/task and syntax realization plan (not code)

1. The existing \`[Physics]\` root is managed by MOOSE. Do **not** replace or
   monkey-patch that built-in root. The \`Plasmas\` grouping and fixed
   descendants are PhysicsApp-owned extensions; propose pinned-MOOSE
   \`registerSyntax(..., "Physics/Plasmas/...")\` mappings for equation leaves,
   using **exact fixed paths** initially. Whether the MOOSE parser accepts
   structural grouping nodes without an Action, and whether wildcard paths
   introduce unwanted repeat semantics, must be proven with one minimal
   Native check-input and negative controls.
2. Implement a single **metadata/ownership preflight** before generating
   any solver variables or Materials. The design-only validation inventory
   includes species, units, field owners, legacy generated names,
   existing \`Physics/NavierStokes/Flow/*\`, boundary references and
   Gummel/MultiApp coupling. Fail before partial object construction.
3. Use the pinned \`PhysicsBase\` lifecycle
   (\`init_physics\`, \`copy_vars_physics\`,
   \`check_integrity_early_physics\`, and required object-specific tasks)
   for leaf builders where supported. **Do not register a placeholder
   task/class just to make a parser example pass.** New tasks, dependencies,
   run order and class list require separate implementation review.
4. \`Coefficient\` and \`Chemistry\` need typed, non-equation provider/owner
   composition contracts. Reuse existing \`PlasmaClosuresAction\` and
   rate Material capabilities when behavior and field ownership match.
   Do not rewrite transport kernels or replace physics by object-name guess.
5. Existing \`GummelIterationAction\` remains the sole orchestration owner.
   Do not silently assemble a single-FEProblem transport+Poisson+Maxwell
   model when the accepted case relies on different MultiApps.
6. Native implementation review will supply a concrete
   \`planned path -> action/task -> objects created -> FEProblem\` table
   **before** coding. This design intentionally does not pre-approve
   specific new C++ class names or class registrations.

## 6. Cross-FEProblem / MultiApp lifecycle

The *qualified current design* must be a preserved point of reference:

\`\`\`text
OUTER_MAIN (one heavy mixture state H^n)
    -> GUMMEL_DRIVER (orchestration-only, frozen H^n)
       -> SUB_ELECTRON (owns electron density/energy and electron closures)
       -> SUB_POISSON (owns phi; receives electron density and heavy charges)
    <- converged n_e / T_e / phi after inner fixed point
    -> one outer heavy update H^n -> H^(n+1)

Maxwell RF FEProblem / MultiApp (where configured):
    explicit RF field, conductivity, power-deposition and PID transfers
\`\`\`

- At the pinned revision, sibling transfers on the same execution flag
  occur before sibling MultiApp execution. Existing
  \`GummelIterationAction\` explicitly stages electron solve at
  \`TIMESTEP_BEGIN\`, Poisson at \`TIMESTEP_END\`; keep it byte-for-byte
  unless a separate parity-gated change is approved.
- Potential feedback is \`direct_sibling\` or
  \`through_parent\` (Steffensen/driver transform), exactly as configured
  in the existing action. The accepted frozen-heavy invariant is
  **\`H^(n,k)=H^n\`** for each inner iteration k of outer step n.
- Cross-application fields use an explicit mapping record:
  \`{from_app, from_variable_or_export_aux, to_app, to_aux,
  unit, mesh_compatibility, stage, interpolation_policy,
  transform, convergence_owner}\`. No unknown target, implicit
  interpolation, or derived functor direct \`MultiAppCopyTransfer\` into
  a solved variable.
- A functor output such as \`electron_temperature_K\` must first be
  sampled to an export AuxVariable. Raw field names such as \`mean_en\`,
  \`log_ne\`, \`phi\`, \`T_e\` are not assumed to have identical units or
  normalization between applications.
- RF coupling must separately record peak/RMS phasor convention, \`q_RF\`
  volume integral, driver PID update stage and whether power is
  prescribed, solved or externally transferred. No duplicate heating
  projection or covert change of \`400 W\` control.

## 7. Error taxonomy and negative test catalogue

G0 proposes stable categories; exact exception message text is an
implementation detail, but every failure must identify path, object/field,
FEProblem and violated contract. **No auto-repair/skip/fallback.**

| ID | Fail-closed condition | Expected behavior |
|---|---|---|
| \`P402_SYNTAX\` | unregistered child, unexpected repeated group, wrong schema version, unknown parameter | fail parser/preflight; no objects |
| \`P402_SPECIES\` | duplicate/unknown species, incompatible phase/charge, non-finite mass, mismatched NS mixture lists | fail before object generation |
| \`P402_OWNER\` | two producers for same density/energy/potential/momentum/RF/chemistry source, including old+new path | fail before object generation |
| \`P402_COEFFICIENT\` | unsupported \`Boltzmann\`/\`MonteCarlo\` mode, missing table digest, out-of-range energy, wrong unit | fail; no fallback/clamp |
| \`P402_CHEMISTRY\` | unknown reaction ID, absent species, duplicate progress owner, missing electron-energy loss | fail |
| \`P402_BC\` | missing required BC, empty/unknown mesh region, unsupported FV/FEM restriction, wrong boundary type | fail |
| \`P402_TRANSFER\` | absent map, wrong AuxVariable sink, wrong application, wrong unit/stage, mismatch mesh mapping | fail |
| \`P402_EXECUTION\` | changed Gummel or RF/MultiApp execution schedule, duplicate driver, implicit single-FEProblem rewrite | fail |
| \`P402_COMPAT\` | legacy-only input differs after opt-in parser added, or rollback cannot reconstruct original | fail |

**Positive control**: the full *illustrative* block hierarchy with a
minimal, explicit externally-provided coefficient table and matching
single-owner electron continuity in an isolated local FEProblem. It is
NOT executable until a separate C++ review provides a real fixture.
**Negative controls**: each table row above requires at least one
independently asserted invalid input, plus two conflicting-owner
cases (same object name, different object names / same physical
equation), and two MultiApp schedules (direct-sibling,
through-parent).

## 8. Smallest proposed illustrative input — NOT executable

The following is an **approved design-target illustration only**, not runnable MOOSE syntax. \`species_catalog\`,
\`source_mode\`, \`output\` and the declared field-bindings are still
candidates; a valid Native MOOSE syntax cannot be inferred.

\`\`\`ini
[Physics]
  [Plasmas]
    [Transport]
      species_catalog = plasma_species_v1.json
      region = plasma
      [Coefficient]
        solver = Boltzmann
        source_mode = verified_table
        source_file = electron_moments.txt
        source_sha256 = <validated_sha256>
        mean_energy = mean_energy_eV
        out_of_range = error
        outputs = coefficients_manifest.json
      []
      [Chemistry]
        mechanism_file = minimal_electron_chemistry.json
        mechanism_sha256 = <validated_sha256>
        reaction_ids = 'EI-02'
        coefficient_provider = 'Transport/Coefficient'
        progress_prefix = R_
        electron_energy_loss_policy = explicit_per_reaction
        conservation_policy = strict
      []
      [DriftDiffusion]
        [Continuity]
          owner_mode = generate
          name_prefix = electron_
          fem_species = 'e'
          fem_charge_numbers = '-1'
          electric_field = E_dc_from_poisson
          mobility = 'electron_mobility'
          diffusivity = 'electron_diffusion'  # existing Functor name; rename deferred
          reaction_sources = 'S_e_from_chemistry'
          boundary_contract = electron_bcs_v1.json
        []
      []
    []
  []
[]
\`\`\`

For a real fixture, \`<validated_sha256>\` placeholders and
\`coefficients_manifest.json\` must be replaced with verified files
and every binding resolved to a typed owner and unit. The example
deliberately does not invent a Poisson equation or a Maxwell/RF
system; \`E_dc_from_poisson\` must be an explicitly mapped external
field. It is therefore an illustration of the **schema**, not yet a
self-contained runnable simulation.

**2026-11-10 G0 refinement (user requested):** Continuity variable names and kernel names are generated internally; remove explicit `variables` and per-family kernel-name options. Use shared `mobility` / `diffusivity` coefficient input names and both `fem_charge_numbers` / `fvm_charge_numbers`. The renamed `electron_diffusivity` provider is a future target, not a proved rename of the current `electron_diffusion` material. G1 build/negative cases, G2 complete naming/ownership mapping, G3 actual solver comparison and G4 cutover remain separate gates. The existing immutable S6 P3 comparison inputs must **not** be rewritten.

**2026-11-09 G0 amendment accepted by user:** No input \`schema_version\`.
Species-bearing equation paths use \`fem_species\` and \`fvm_species\`
rather than \`species\`. No global \`Transport/discretization\` parameter.
Latest S6: FEM \`e\` continuity/energy; FV \`O2p Om Op\` ion
continuity; FV \`O2 O2s O Os\` single neutral mixture. Native syntax and
numerical parity remain NOT_EVALUATED until G1–G3.

## 9. G0 acceptance matrix and downstream gates

| Gate | Deliverable | Status |
|---|---|---|
| **G0-A** | approved D1–D8 architectural invariant table | **APPROVED** per user |
| **G0-B** | per-leaf concrete parameters, types, required/default design policy | **G0_DESIGN_APPROVED; NATIVE_NOT_EVALUATED** |
| **G0-C** | species catalogue, variable & equation ownership matrix and conflict design | **G0_DESIGN_APPROVED; NATIVE_NOT_EVALUATED** |
| **G0-D** | Action/PhysicsBase approach, explicit MultiApp timing and rollback design | **G0_DESIGN_APPROVED; G1 C++ DETAIL PENDING** |
| **G0-E** | positive/negative controls and native numerical parity gate design | **G0_DESIGN_APPROVED; EXECUTION_NOT_EVALUATED** |
| **G1** | explicit authorization, C++ registration, Native build and real \`--check-input\` plus negatives | **BLOCKED** |
| **G2** | generated-object / task graph parity to explicit input | **BLOCKED** |
| **G3** | actual Native small fixture + pinned 400 W S5 physical/numerical comparison | **BLOCKED** |
| **G4** | per-consumer opt-in migration, rollback and scientific review | **BLOCKED** |

**G0 design decisions approved (2026-11-09):**

1. Use \`species_catalog/region\` without a user \`schema_version\` or global discretization; specify \`fem_species\` and \`fvm_species\` on species-bearing equations.
2. Use typed \`owner_mode = generate|external\`; reject duplicate variables, equations, sources and RF owners.
3. Enforce \`verified_table|on_demand\` source contract with unavailable on-demand providers blocked, no fallback.
4. Keep v0.1 DD/Energy electron-only and the single-mixture NS continuity/momentum semantics.
5. Preserve Gummel/MultiApp/RF execution order and the fail-closed error taxonomy.

**Added user acceptance requirement: existing-run input option placement.**
Before G1 object generation parity and G4 cutover, inventory every **effective** input
option in the current S4/S5/S6/native run family (including recursively included
and generated files), and produce an explicit old-option -> new-block or
native-MOOSE-retained-path mapping with units, source-ownership,
execution-stage and SHA provenance. No missing, duplicated, silently defaulted,
or silently reassigned options are permitted; see companion
\`2026-11-09_issue402_current_run_option_placement.md\`.
A new DSL need **not** absorb MOOSE-native \`Mesh/Executioner/Outputs\`,
\`MultiApps/Transfers/Controls\` or diagnostic reporting; they are
**retained in their native scopes** unless an explicitly approved new owner
replaces them with equivalence evidence. The current run families are *not*
automatically migrated by G0 approval.

**G1 separate implementation selection:** No C++ class, Action/task registration,
actual \`--check-input\` acceptance, production input switch or merge of experimental
results is authorized by G0; select the first bounded Native implementation
slice only after separate approval.

## 10. Evidence references

- [#402 approved D1–D8 decision](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/402)
- [Pinned MOOSE PhysicsBase](https://github.com/idaholab/moose/blob/9f388366ccf38b9c34542ec5561198249fde0ac9/framework/include/physics/PhysicsBase.h)
- [Pinned MOOSE NavierStokesApp syntax](https://github.com/idaholab/moose/blob/9f388366ccf38b9c34542ec5561198249fde0ac9/modules/navier_stokes/src/base/NavierStokesApp.C)
- [Current PhysicsApp registrations](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/main/physics_app/src/base/PhysicsApp.C)
- [Current Gummel/Transfer contract](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/main/physics_app/docs/gummel_iteration_action.md)
- [Current closure Action contract](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/main/physics_app/docs/plasma_closures_action.md)
- [S5-417-407 native baseline](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42521896067)
