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
