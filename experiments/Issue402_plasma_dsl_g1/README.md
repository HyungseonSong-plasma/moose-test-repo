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
