# Issue #402 — Verbatim DriftDiffusion BC list relocation to JSON

**Authority:** the existing FEM electron wall input and Issue #395
`enable_electron_adjacent_sheath_wall.py` transformation; FV discriminator
`experiments/fem_fvm_plasma_discriminator/prepare_cases.py` is a
**separate, physically different** boundary set. **No new wall law**.
Draft PR #531 is stacked on Draft PR #530. **SCIENCE_HOLD.**

## Source inspection FIRST

The Issue #395 script preserves each existing BC block name and its original
wall sideset, replacing the electron pair's object classes with the two
existing registered types:

```ini
[BCs]
  [<existing electron particle BC name>]
    type = FEMElectronSheathBC
    variable = log_ne
    wall_number_flux = electron_wall_number_flux
    boundary = '<existing plasma wall sidesets>'
  []
  [<existing electron energy BC name>]
    type = FEMElectronEnergySheathBC
    variable = log_energy
    wall_number_flux = electron_wall_number_flux
    mean_energy = mean_en_solved
    boundary = '<same plasma wall sidesets>'
  []
[]
```

The transformation expects **four existing particle and four existing
energy BC blocks** in that historical generation chain. Their exact
group names and sideset lists depend on the prior recipe; the generated
complete production `.i` is not in the tracked source tree, so do not
claim its byte-exact active layout from the generator alone. The
historical mesh maps `inlet`, `outlet`,
`plasma_electrode`, `plasma_metal`, `plasma_right`,
`plasma_cover`, `plasma_wafer` and
`plasma_focus_ring` as plasma-facing sidesets. The six solid
interface labels, not the inlet/outlet pair, form the historical
electron-wall candidate set.

**Important independent FV path:** the discriminator's explicit
`[FVBCs]` used `PhysicsFVElectronGroundedSheathCollectionBC`,
`PhysicsFVElectronGroundedSheathEnergyBC`, `FVFunctorNeumannBC`
for the ion wall, and `FVDirichletBC` for grounded potential.
These are **not** interchangeable with the FEM Issue #395 BCs; this
first relocation intentionally preserves them as explicit external
FV input and does not try to convert them into FEM BCs.

The wall flux `electron_wall_number_flux` is already provided by
`PhysicsElectronAdjacentSheathWallFluxMaterial`, using a plasma-sided
`FaceArg`. `PhysicsElectronMeanEnergyMaterial` maps live
`log_energy, log_ne` to `mean_en_solved` and preserves strict
finite/positive error handling. Even with logarithmic states, `NaN`,
infinite data, and `exp` underflow/overflow remain possible;
a log variable does not automatically prove finite positive energy
at every nonlinear iteration. Both existing Materials stay in the
original `[FunctorMaterials]` section unchanged.

## New configuration is only a relocation

There is **NO** `plasma_boundary` activation option. There are
**NO** `open`/`adjacent_sheath`/role model labels. The key
`drift_diffusion_boundary` in the same existing
`[Physics]/[Plasmas]/files` JSON is the sole switch.

Representative structured JSON (the P2 fixture uses 2D GeneratedMesh
with left/bottom/right/top rather than production QVT sideset names):

```json
{
  "drift_diffusion_boundary": {
    "wafer": {
      "mesh_boundary": "plasma_wafer",
      "bcs": {
        "electron_wafer": {
          "type": "FEMElectronSheathBC",
          "variable": "log_ne",
          "wall_number_flux": "electron_wall_number_flux"
        },
        "electron_energy_wafer": {
          "type": "FEMElectronEnergySheathBC",
          "variable": "log_energy",
          "wall_number_flux": "electron_wall_number_flux",
          "mean_energy": "mean_en_solved"
        }
      }
    },
    "inlet": {"mesh_boundary": "inlet", "bcs": {}},
    "outlet": {"mesh_boundary": "outlet", "bcs": {}}
  }
}
```

Actual `species`, `equations`, `reactions`, and optional
`transport_coefficients` remain unchanged in the same JSON file.
Each `bcs` map stores **the existing BC name** and exactly the
supported BC type's `.i` parameters; `boundary` is inherited from
the enclosing `mesh_boundary`. That value accepts either a single
mesh sideset name, the original `.i` whitespace-separated boundary
string, or an ordered JSON array of sideset names. A single
multi-sideset BC is **never split into multiple MOOSE BC objects**.
Empty `bcs` generates no BC.

`ChemistryData` performs strict static validation and the **existing**
`PlasmasAction` iterates entries in its already registered
`add_bc` task, creating the exact existing `FEMElectronSheathBC`
or `FEMElectronEnergySheathBC` objects with unchanged parameter
types, flux name and energy coefficient. The Action is invoked from
the same root `[Plasmas]` even without `[Transport]/[DriftDiffusion]`
subblocks; **presence of the JSON list is sufficient**. No second
boundary Action, no background auto detection of wall models and no
implicit `[FunctorMaterials]` construction.

Without `drift_diffusion_boundary`, zero new BCs are created.
The old explicit `[BCs]` input continues unchanged. For an opted-in
JSON relocation, remove the corresponding **identical** explicit
`[BCs]` blocks to prevent double residual ownership. Neither a
JSON entry nor this Action removes old explicit BCs automatically.

## Scope and evidence

- Current typed importer covers the two **verified FEM electron wall**
  BC classes above. Unsupported BC `type` fails closed rather than
  substituting a different operator. Existing FV/ion/Poisson/flow
  BC lists remain explicit until their own exact parameter inventories
  and P2 migration oracles are performed.
- `physics_app/ci/dd_plasma_boundary_json_p2.i` is new JSON-owned
  synthetic control; `dd_plasma_boundary_legacy_p2.i` retains the
  exact same four named MOOSE BC declarations. The P0 test checks
  byte-for-field mapping of all four BCs.
- P0 source and mapping invariant, P1 native build, P2 native
  `physics-opt --check-input` both positive inputs, no-JSON and
  fail-closed malformed BC definitions, duplicate owner and extra
  parameter mutations.
- P3 electron/energy wall flux and dielectric charge current parity
  with the original powered Issue #395 source is **not verified**.
  **SCIENCE_HOLD** until an exact historical input is available
  and independently checked.
