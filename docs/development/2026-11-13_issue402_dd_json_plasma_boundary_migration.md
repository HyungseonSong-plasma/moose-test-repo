# Issue #402 — Existing BC list relocation to generic JSON boundaries

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
`ESWallFluxMaterial.C` (canonical name; moved without changing the
adjacent-cell sheath flux equation from the historical implementation), using a plasma-sided
`FaceArg` and `PhysicsGroundedElectronSheath::primaryParticleFluxHat`.
`PhysicsElectronMeanEnergyMaterial.C` reads the solved log-molar states
and publishes a configurable mean-energy Functor
(e.g., `e_energy_eV = exp(log_energy - log_ne)` [eV]) as a
**derived AD Functor**; it is not an independent solver variable.
`FEMElectronEnergySheathBC.C` uses this Functor for
`T_e=(2/3) e_energy_eV` for the new fixture and the existing outgoing energy flux
`(Gamma_e/N_A)*(5/2)*T_e`.

The `MeanEnergyMaterial` guard is **demand-driven**: it detects invalid
inputs or the derived nonfinite/nonpositive mean energy when *that Functor
is evaluated*. It is not a global validation of all nonlinear states,
and a different Kernel or Functor might fail first. A negative finite
`log_ne` or `log_energy` is valid (it encodes a small positive
physical density). `NaN/Inf` in either state, or
`exp(log_energy-log_ne)` underflow to zero / overflow to infinity,
can still occur. These guards provide a local error message but cannot
guarantee prevention of an earlier solver failure elsewhere. No
mean-energy error policy or physical formula is changed here.
The physical constitutive formula and error policies are unchanged. The
new fixture sets `mean_energy_output=e_energy_eV` explicitly. When the output name is omitted, both canonical `e_energy_eV` and legacy
`mean_en_solved` are exported by the same single evaluation lambda to
preserve old inputs. An explicit `mean_energy_output` exports only the
selected name. **Do not
rename mean energy to `e_energy_density`:** mean energy is in eV per
electron, while electron energy density is in eV/m3. The
`PhysicsElectronMeanEnergyMaterial` supports normalized, physical_eV
and log_molar_eV state representations and does *not* output an energy
density, so calling it `EEDConvertorMaterial` would be misleading.

`ESWallFluxMaterial` is now the canonical **sheath-suppressed**
wall flux source. Both the transitional `ElectronWallFluxMaterial` spelling
and historical `PhysicsElectronAdjacentSheathWallFluxMaterial` are thin
registered compatibility subclasses with **no duplicated physics**. The older
`PhysicsElectronWallFluxMaterial` **remains a separate thermal-only
absorbing-wall model** used by Issue #3 dielectric surface charge
experiments (`d3_combined_primary.i`, `d5_fv_wall_current_feedback.i`,
`d6_2d_integrated.i` and associated generator scripts). The Issue #395
recipe intentionally replaces it with the sheath model. Both publish
`electron_wall_number_flux` in their respective configurations;
they must not be instantiated together as owners of the same Functor.

## New configuration is only a relocation

There is **NO** `plasma_boundary` activation option. There are
**NO** `open`/`adjacent_sheath`/role model labels. The key
`boundaries` in the same existing
`[Physics]/[Plasmas]/files` JSON is the sole switch.

Representative structured JSON (the P2 fixture uses 2D GeneratedMesh
with left/bottom/right/top rather than production QVT sideset names):

```json
{
  "boundaries": {
    "plasma_wafer": {
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
          "mean_energy": "e_energy_eV"
        }
      }
    },
    "inlet": {"bcs": {}},
    "outlet": {"bcs": {}}
  }
}
```

Actual `species`, `equations`, `reactions`, and optional
`transport_coefficients` remain unchanged in the same JSON file.
The outer JSON key itself is the **actual mesh boundary name**:
`plasma_wafer` maps directly to the original MOOSE `boundary=plasma_wafer`.
There is no redundant `mesh_boundary` field or role/mode selector.
Each `bcs` map stores the **existing BC name** and its original
`type`, `variable`, `wall_number_flux`, and (for electron energy)
`mean_energy` values. A key containing whitespace-separated sideset
names (e.g. `"plasma_electrode plasma_metal"`) represents **one original
multi-sideset BC**, not two newly generated BCs.
An empty `bcs` map generates no BC.

`ChemistryData` performs strict static validation and the **existing**
`PlasmasAction` iterates entries in its already registered
`add_bc` task, creating the exact existing `FEMElectronSheathBC`
or `FEMElectronEnergySheathBC` objects with unchanged parameter
types, flux name and energy coefficient. The Action is invoked from
the same root `[Plasmas]` even without `[Transport]/[DriftDiffusion]`
subblocks; **presence of the JSON list is sufficient**. No second
boundary Action, no background auto detection of wall models and no
implicit `[FunctorMaterials]` construction.

Without `boundaries`, zero new BCs are created.
The previous experimental key `drift_diffusion_boundary` is explicitly
rejected with a migration error; no silent omission.
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
- `physics_app/ci/dd_plasma_boundary_json_p2.i` uses the canonical
  `ESWallFluxMaterial`; the explicit-BC control uses the legacy
  alias class. Both use the exact same wall law and name the derived
  mean energy `e_energy_eV` explicitly.
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

## Current solver variable names and format-branch audit

The new `Physics/Plasmas/Transport/DriftDiffusion/Energy` Action in
`physics_app/src/physics/plasma/DDEnergyEq.C` calls
`energyStateName("e") = "log_" + "e" + "_energy"`, giving
**`log_e_energy`**, not `log_energy`. The related new Continuity
Action uses **`log_e`**. Older Issue #395 production inputs solve
`log_energy` and `log_ne` instead; these are distinct interfaces.
Never substitute the old pair into an Action-generated new pair without
explicit source mapping. Example new log-molar mean-energy bridge:
```ini
[FunctorMaterials]
  [electron_mean_energy]
    type = PhysicsElectronMeanEnergyMaterial
    state_form = log_molar_eV
    electron_energy_density = log_e_energy
    electron_density = log_e
    mean_energy_output = e_energy_eV
  []
[]
```
For historical inputs, retain `log_energy/log_ne` and set
`mean_energy_output=e_energy_eV` only when all consuming Functors are
also mapped to the canonical name.

`PhysicsElectronMeanEnergyMaterial.C` presently supports three *input*
representations, not three unrelated physical outputs:

- `log_molar_eV`: `exp(log_energy_state - log_density_state)`
  [eV], actively consumed by existing FEM log-molar inputs and
  compatible with the new `log_e_energy/log_e` states.
- `physical_eV`: physical electron energy density [eV/m^3]
  divided by physical number density [1/m^3], actively referenced by
  `physics_app/ci/electron_energy_transport_smoke.i`,
  `electron_energy_lookup_response_smoke.i` and several runtime
  verification generators; **not retired**.
- `normalized`: historical dimensionless energy and number density
  ratio multiplied by `energy_reference_eV`. It remains a
  backward-compatibility branch pending a complete inventory of
  historical generators and exact numerical regression.

All three calculations *can* be expressed as AD Functors, for example
using `ADParsedFunctorMaterial`: `exp(log_energy-log_density)`,
`energy_density/number_density`, or
`epsilon_ref*normalized_energy/normalized_density`, respectively.

The new synthetic P2 alternative
`physics_app/ci/dd_plasma_boundary_parsed_mean_p2.i` uses an
`ADParsedFunctorMaterial` to publish `e_energy_eV` with
`functor_names='log_energy log_ne'`,
`functor_symbols='ue un'`, and `expression='exp(ue-un)'`.
A passing `--check-input` confirms **object construction and wiring
only**: it does NOT prove equivalent error behavior, derivative/Jacobian
values, or solution trajectory.
**However**, a pure parsed expression does not preserve the present
fail-fast finiteness, positivity, exact parameter/normalization checks.
We have not migrated or removed these format branches or proven AD
derivative parity for an alternative implementation.
This remains a scoped investigation, **not** an authorization to
delete old solver compatibility modes.

The thermal-only `PhysicsElectronWallFluxMaterial` remains a live
dependency of `experiments/Issue3_dielectric_surface_charge/` native
input files and a literal pre-conversion type consumed by the
`experiments/Issue395_powered_chemistry_ladder/enable_electron_adjacent_sheath_wall.py`
script. It cannot be retired/deleted on a claim of disuse. The
thermal-only and sheath-corrected constitutive laws are physically
different. They are never simultaneous providers of the same output
`electron_wall_number_flux` in one block.
