# Check existing plasma species variables

This feature checks whether each plasma species uses a solver variable that
already exists. It does not add equations, variables, or boundary conditions.

The shared checks are implemented in `PlasmaInterface`, which inherits from
MOOSE's `PhysicsBase`. The `Plasma::ContinuityPhysics` class uses those checks
for continuity inputs. It does not create equations yet.

## Input

The input path is unchanged:
`Physics/Plasmas/Transport/DriftDiffusion/Continuity`.

- `fem_species`: species using finite-element variables.
- `fvm_species`: species using finite-volume variables.
- `variables`: existing solver variables in the same order as the species.
- `owner_mode = external`: use existing variables only. `generate` is not supported.

Each species and variable must be unique. Every solver variable must exist and
have the correct type. The checker explains the problem when an input is invalid.

The parameter names remain unchanged so that existing inputs still work.

## Run the tests

The build uses a fixed container image:

`ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008`

The MOOSE version is `9f388366ccf38b9c34542ec5561198249fde0ac9`.

From the repository root on a machine with Docker:

```bash
bash experiments/Issue402_plasma_dsl_g1/run_native_binding_smoke.sh
```

This builds the solver, checks one valid and four invalid inputs, then runs the
same small diffusion example with and without the checker. The results must
match. Logs and comparisons are saved in `evidence/`.

## Verification status

The first compiled build attempt at
`5752b0e4f722045d9a2dba1e2d70c4e2d86d5853` failed before these checks.
Existing Boltzmann source files define the same helper names and conflict
when compiled together in the combined build mode. The test build now compiles
those helper files separately; this does not change the simulation equations.

The solver-variable checks and numerical comparison are therefore not yet
verified by a completed build. Separate 400 W, 100 microsecond plasma runs
are required before claiming full simulation equivalence.

The `s6_external_bindings.i` file is an extra input for later tests. It must
not replace any original simulation inputs or disclose private chemistry data.
Scientific approval remains on hold.
