# Plasma input checks

MOOSE can now parse and execute five plasma input actions. Each action checks
existing simulation inputs; none creates or replaces an equation.

| Input path under `Physics/Plasmas` | C++ action | What it checks |
| --- | --- | --- |
| `Transport/DriftDiffusion/Continuity` | `Plasma::ContinuityPhysics` | Species and existing FEM/FV solver variables |
| `Transport/DriftDiffusion/Energy` | `Plasma::EnergyPhysics` | Electron species and existing FEM energy variable |
| `Transport/Chemistry` | `Plasma::ChemistryPhysics` | Unique reactions and one progress name per reaction |
| `Poisson` | `Plasma::PoissonPhysics` | Existing electric potential solver variable |
| `Maxwell` | `Plasma::MaxwellPhysics` | Existing real/imaginary fields, matching variable families and positive frequency |

All actions share the `PlasmaInterface` validation base class. The
`owner_mode` input has been removed. These actions **always use existing
solver objects**, without adding a physics equation, source, boundary
condition or changing numerical parameters. In particular, the chemistry
action verifies the reaction-to-progress name mapping, not the existence,
units or ownership of the underlying rate functors.

To exercise all five actions with a small simulation, supply
`baseline.i` and `valid_all_physics.i`. The latter is intentionally a
minimal demonstration, **not a physical multi-equation plasma model**.

The build uses the fixed image
`ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008`
and MOOSE revision `9f388366ccf38b9c34542ec5561198249fde0ac9`.

From the repository root on a Docker runner:

```bash
bash experiments/Issue402_plasma_dsl_g1/run_native_binding_smoke.sh
```

The script compiles the real C++ code, accepts valid inputs, rejects invalid
inputs, and compares two small numerical solves. Real S6 400 W / 100 microsecond
replay with these inputs is a separate validation requirement. The existing
S6 input layers and private chemistry data must remain unchanged. No
scientific result is accepted by this input registration alone.


## Connecting existing MOOSE solver objects

Only explicitly supplied physical coefficients activate object generation.
The existing validation-only inputs do not add any terms.

- **Continuity:** `fem_potential`, `fem_mobility`,
  `fem_diffusion`, and `fem_charge_numbers` create
  `PhysicsFEMLogMolarDriftDiffusion` for each FEM species.
  The original time derivative, source and wall terms remain external.
  There is **no automatic FV heavy-species builder** yet.
- **Energy:** `rf_heating_material` creates a `MatBodyForce` source
  in an existing FEM electron-energy equation. The material property
  must already have the equation's correct units.
- **Chemistry:** `rate_table_files`, `mean_energy`,
  `electron_number_density`, and `target_molar_concentrations`
  create existing strict-table `PhysicsElectronImpactRateMaterial` objects.
  Reaction source projection remains external.
- **Poisson:** `charge_source_material` creates `Diffusion` and
  `MatBodyForce`. The property must supply `rho/epsilon0`
  for constant vacuum permittivity; variable permittivity is unsupported.
  Optional `ground_boundaries` adds zero-potential conditions.
- **Maxwell:** `reaction_material` and `coupling_material`
  create paired `Diffusion`, `MatReaction`, `MatCoupledForce`
  exactly as in the existing scalar RF input. Optional `imaginary_source`
  and `ground_boundaries` create forcing and zero-field boundary objects.
  Material coefficients must preserve existing geometry, frequency and
  conductivity conventions. Spatially restricted coil sources and RF
  power deposition materials are not generated.

Never activate generated terms when the same existing equation terms
are also declared under `[Kernels]` or `[BCs]`: doing so double-counts
the physics. The `rf_generated.i` versus `rf_explicit.i` comparison
checks that the Maxwell action generates the same solver operator as
explicit MOOSE objects. This is not full S6 scientific parity.

## Single-kernel S6 migration (archived, not production)

The completed S6-417 and S6-941 runs contain an explicit `ne_transport`
FEM log-molar drift-diffusion Kernel. The archive-based preparation program
moves **only this one existing Kernel** into `ContinuityPhysics` and
preserves its name, parameters and `plasma` block restriction.
The original electron time derivative, energy, chemistry, ion FV equations,
Poisson/MultiApps, controls, materials and all wall conditions remain native.

The `fem_kernel_names = 'ne_transport'` input preserves the existing
Kernel identity. During `check_integrity`, the common plasma validation
also rejects more than one same-type FEM Kernel on a variable, including an
accidental native + Physics duplicate.

To prepare separate baseline and candidate **outside the repository**, with
the two original GitHub Actions S6 ZIP artifacts available locally:

```bash
python3 experiments/Issue402_plasma_dsl_g1/prepare_s6_single_kernel_migration.py \
  --archive /private/path/s6_417.zip \
  --archive /private/path/s6_941.zip \
  --output-dir /private/path/s6_migration_review
```

The generated `migration_report.json` proves only the isolated static
source transformation. It does not prove that the new model compiles or
replays the original 400 W / 100 microsecond trajectory. That full native
comparison requires the archived rate tables and pinned original runtime
dependencies. No private chemistry files are committed or published.

The small native regression now includes a **negative test** that provides
native and generated Maxwell kernels simultaneously and requires rejection.
The C++ duplicate guard is intentionally conservative: two kernels of the
same type targeting one FEM variable are rejected even if deliberately
different sources would otherwise be useful. Keep such complex sources
explicit until typed ownership is implemented.

## Mandatory full 400 W / 100 µs S6 numerical parity gate

**Current status: NOT EVALUATED.** Both historical GitHub Actions archives
(artifacts `13677089020` and `13677375813`) were independently inspected
on 2026-11-09. Each has ten SHA256-matching input layers and a native
`plasma.e` containing 461 timepoints, from 0 through 100 µs. The
original `ne_transport` block has the same SHA256 and physical parameters
in both cases. The archives explicitly omit private reaction-rate bytes.

The read-only archive preparation can run without private data:

```bash
python3 experiments/Issue402_plasma_dsl_g1/run_s6_full_native_parity.py \
  --archive /path/to/original_417_artifact.zip \
  --archive /path/to/original_941_artifact.zip \
  --output-dir /scratch/s6_archived_review
```

To exercise the **mandatory** native check-input and 460-step replay, run
this on an independently trusted machine with the original pinned
`29d1acc6` source tree prepared exactly as in the approved Issue477
workflow, all original private rate tables restored in that tree, and a
new native `physics-opt` compiled from the PR source using the pinned
`physics-build-base` image:

```bash
python3 experiments/Issue402_plasma_dsl_g1/run_s6_full_native_parity.py \
  --archive /secure/original_417_artifact.zip \
  --archive /secure/original_941_artifact.zip \
  --source-root /secure/pinned_original_prepared_checkout \
  --binary /secure/pr491_build/physics_app/physics-opt \
  --output-dir /secure/scratch/s6_migration_full_replay \
  --run
```

The runner does **not** retrieve GitHub secrets, modify original archived
input layers, upload private tables or run from PR CI with secrets. It
verifies each original input digest and the private-rate hashes before
execution. The candidate removes only `ne_transport` from a newly
created input beside the originals and recreates it via
`ContinuityPhysics`. Generated temporary candidate inputs are removed
after execution.

On a trusted runner with capacity for two OCI containers, the **417 and 941
cases execute concurrently** as two independent lanes (`max_workers=2`).
Within each lane, baseline and candidate preflights and then both fresh
460-step native solves run **sequentially**. Case-specific hidden input names,
private logs, output trees and parity reports remain distinct. The shared
prepared checkout is mounted read-only by both offline containers. A failed
lane does not cancel the other; overall parity fails closed if either fails.
No additional secrets or permissions are required by this scheduling change.

The runner checks original/native `--check-input`, demands
461 Exodus timepoints from 0 to 0.0001 s, and compares **all Exodus
fields and all CSV diagnostics** for historical-vs-new-baseline and
new-baseline-vs-generated-candidate. If private data or a trusted
executor is unavailable, this gate remains `NOT_EVALUATED`; a
small Maxwell example or static source audit does not substitute.
Keep `SCIENCE_HOLD` even after numerical parity is proven.

## 2026-11-10 option-first Continuity experiment (separate stacked draft)

This experiment changes only the `ContinuityPhysics` **input contract** and
internal names, not any Material or Functor registration, source code or
physical coefficient values. The generated lower-level
`PhysicsFEMLogMolarDriftDiffusion` parameter remains named `diffusion`.
The user-visible **Physics option** is now `diffusivity`; it can still point
to the existing `electron_diffusion` functor. Changing that provider to
`electron_diffusivity` is deliberately deferred.

- Input `variables` and `fem_kernel_names`/`fvm_kernel_names` are removed;
  `e -> log_ne`, and archived S6 `O2p/Om/Op -> log_ni/log_nm/log_nop`
  are resolved internally. Other species use `log_n<species_id>` pending
  separate vetted catalog validation.
- Generated kernel name is fixed to `<species_id>_transport`, so an electron
  kernel is named `e_transport`. In the existing protected S6 migration
  comparison, the old `ne_transport` remains *unchanged*: it is NOT a valid
  proof for the new scheme, and the prepared P3 B/C input decks are untouched.
- `mobility` / `diffusivity` use FEM-first then FVM ordered coefficient
  vectors; `fem_charge_numbers` and `fvm_charge_numbers` must each match
  declared species and known charge signs when generation is activated.
  There is still **no FV transport Kernel generation**. Providing coefficients
  for unimplemented FV physics does not claim FV support or scientific parity.
- A standalone small-input regression tests valid existing-variable binding,
  deprecated user options, missing FV charges, coefficient vector lengths,
  invalid charge signs and FEM/FVM variable-family mismatch. No native result
  may be reported until the exact branch HEAD is built and checked with OCI.

This is a staged API trial only: `SCIENCE_HOLD`, protected-rate separation,
Issue #493 P3 source/inputs, production defaults and PR #491 remain unchanged.

## S6-417/941 new option-native P2 (public-data-only validation)

After the small Native fixtures pass, `run_native_binding_smoke.sh` now also
runs `run_public_option_s6_p2.sh` on the **same exact-head executable**.
The script checks out only public historical source
`29d1acc6ef7969908b86719e4b95c73a1565136d` in temporary scratch,
prepares the original 400 W public mesh, verifies the existing immutable
Issue #493 `public_p2_decks.tar.xz.b64` and 19 public Boltzmann rate
digests, and runs four real native `--check-input` cases:

- S6-417 **B**: original explicit `ne_transport`, public new Boltzmann rates
- S6-417 **D**: original C base without `ne_transport`, replaced by the
  SHA-pinned new option-only `[Physics]` overlay generating `e_transport`
- S6-941 **B**: equivalent case-specific original explicit input
- S6-941 **D**: equivalent case-specific new option-only input

The new overlay is not the old P3 C input and is never written back to the
committed reference deck archive. Existing provider names such as
`electron_diffusion`, `ion_diffusion`, `negative_ion_diffusion`, and
`atomic_positive_ion_diffusion` stay unchanged. FV ion kernels remain native
and are not generated by this minimal Continuity slice.

Each case uses an isolated temporary workspace. Inputs include precisely the
five public selected rate tables for that case; no protected historical table,
GitHub secret, old MCS source, unreviewed executable download, P3 solve or P4
scientific analysis is involved. The fixed OCI image digest and fresh native
binary SHA are checked; status and safe check logs are saved under
`evidence/`. Temporary mesh and staged inputs are not published as evidence
artifacts. `SCIENCE_HOLD` remains in all outcomes.

**Acceptance:** four successful real native P2 check-input exits and
`Syntax OK` markers. This verifies input/action construction only. Kernel
object identity, residual/Jacobian equivalence and fresh 460-step 400 W S6
numerical comparison require subsequent independent checks and cannot be
inferred from `P2=PASS`.
