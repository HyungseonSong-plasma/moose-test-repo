# Issue #402 — Canonical electron energy and boundary ownership

**Status:** Draft PR #531, stacked on Draft PR #530. **SCIENCE_HOLD** until
full powered/plasma P3 physics and numerical equivalence are validated.
No new wall law or electron energy equation was introduced by this refactor.

## 1. Current authority and solved-state names

The source in `physics_app/src/physics/plasma/DDEnergyEq.C` resolves the
electron energy solver state as `log_e_energy`:
`energyStateName("e") = "log_" + "e" + "_energy"`.
`DDContinuityEq.C` similarly uses `log_e`.

Historical FEM Issue #395 and native archived S6 input layers instead
recorded `log_energy` and `log_ne`. They must remain verifiable as
immutable evidence. The active Issue #402 scratch converter reads and
verifies those archival inputs first, then rewrites *disposable* prepared
inputs to `log_e_energy`, `log_e`, `e_energy_eV`, canonical Material
classes and the current Chemistry progress names. The original archived
evidence files are not overwritten.

Do not claim that every historical repository file has been renamed:
immutable source and regression oracle tokens are intentionally retained.

## 2. ElectronEnergyMaterial.C: one output, one log-molar state

Canonical registered class: `physics_app/src/materials/ElectronEnergyMaterial.C`.
The only supported representation is `log_molar_eV`; `physical_eV` and
`normalized` have no runtime factory mode in this class.

- Solver states: `log_e_energy` [ln(eV mol/m^3)] and `log_e` [ln(mol/m^3)].
- Output: `e_energy_eV = exp(log_e_energy - log_e)` [eV].
- Invalid/overflowed mean-energy Functors fail closed, without clamping.
- No `mean_en_solved`, configurable output alias or `energy_reference_eV`.
- `DDEnergyEq.C` creates this Material automatically for the full FEM
  electron-energy path (`fem_potential` provided); explicitly authored
  native/partial cases can still declare the canonical Material separately.

`DDTransportMaterial.C` consumes `e_energy_eV` directly. Lookup coordinates
are not user selectable.

## 3. ESWallFluxMaterial.C is the only registered electron-wall Material

Canonical registered class `ESWallFluxMaterial` is in
`physics_app/src/materials/ESWallFluxMaterial.C`. It retains the
original plasma-sided `FaceArg` adjacent-cell sheath-suppressed
wall particle flux from Issue #395, without modifying its equation:

`Gamma_e = sticking * n_e * mean_speed_e/4 * exp(-sheath_drop_V/T_e)`,
`T_e=(2/3)*e_energy_eV`.

The factory classes/files for `ElectronWallFluxMaterial`,
`PhysicsElectronAdjacentSheathWallFluxMaterial` and the distinct
thermal-only `PhysicsElectronWallFluxMaterial` have been **deleted**.
There are **no runtime aliases**. Historical Issue #3 thermal-only
source input remains preserved for provenance; it is no longer a valid
input for the new binary without a separately authorized physics
migration. Replacing a thermal-only law by sheath suppression is a
**physical change**; this PR makes no Issue #3 numerical parity claim.

The Issue #402 scratch S6 preparer recognizes the exact historical
source types *as text only* and transforms staged scratch to the
canonical type, with explicit SCIENCE_HOLD on any thermal-to-sheath
change.

## 4. JSON boundaries: physical mesh sideset keys

```json
{
  "boundaries": {
    "plasma_wafer": {
      "bcs": {
        "electron_wafer": {
          "type": "FEMElectronSheathBC",
          "variable": "log_e",
          "wall_number_flux": "electron_wall_number_flux"
        },
        "electron_energy_wafer": {
          "type": "FEMElectronEnergySheathBC",
          "variable": "log_e_energy",
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

The outer key is exactly the MOOSE mesh sideset (`boundary` in an
old `[BCs]` block). A whitespace-delimited key supports multiple
sidesets under ONE existing BC object. The JSON catalogue is optional:
absence creates zero additional BCs. No `plasma_boundary` enable flag,
role/enumerated wall model or redundant `mesh_boundary` field exists.
The old experimental key `drift_diffusion_boundary` is explicitly
rejected. The parser currently supports only the two verified FEM
electron-wall BC types; it does NOT implement arbitrary DD/FV/NV,
Poisson, or Navier–Stokes BCs.

The existing `PlasmasAction` in
`physics_app/src/physics/plasma/Chemistry.C` registers exactly those
JSON-declared BCs during MOOSE `add_bc`. The full FEM energy Physics
(`fem_potential` set) generates the existing `ElectronEnergyMaterial`
and, only if supported sheath BCs are present, the physical-number-density
bridge and existing `ESWallFluxMaterial`. No new sheath law or
duplicate Flux Material factory was created.

## 5. JSON species initials and automatic electron equation assembly

`fem_species` and `fvm_species` in the MOOSE `.i` select **species IDs only**.
The retired positional syntax `fem_species = 'e 1e15'` is not supported.

For FEM and FVM continuity, each `species.<id>` JSON object may declare
`initial_number_density` in **particles/m^3**. The parser rejects null,
strings, NaN/non-finite, zero and negative densities. Repeated species
declarations across mechanism JSON files must agree on explicitly given
values; missing metadata merges without replacing an existing value.
Example (other required JSON mechanism keys omitted here):

```json
{
  "species": {
    "e": {"elements": {}, "charge_number": -1, "initial_number_density": 1e15},
    "O2p": {"elements": {"O": 2}, "charge_number": 1, "initial_number_density": 1e14}
  }
}
```

```ini
[Physics]
  [Plasmas]
    files = dd_plasma_boundary_json_p2.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = e
          fvm_species = O2p
          fem_potential = potential
        []
        [Energy]
          fem_species = e
          fem_potential = potential
          initial_molar_energy_density_eV = 8.3e-9
        []
      []
    []
  []
[]
```

If the JSON initial number density is present, `DDContinuityEq.C`
automatically creates `log_<id>` as `MooseVariable` (FEM) or
`MooseVariableFVReal` (FVM) and initializes it through `ConstantIC` or
`FVConstantIC` with `ln(n_initial/N_A)`. Missing JSON metadata leaves
the existing explicit variable/IC ownership intact. JSON automatic IC
plus an already declared variable is an error, not a silent override.

The FEM electron continuity path generates its existing conservative
log-molar time derivative, drift/diffusion and optional Chemistry sources;
its mobility/diffusivity come from JSON `transport_coefficients`.
The full FEM electron-energy path (`fem_potential` provided) generates
`log_e_energy`, its IC, existing time/drift/Joule kernels, mean-energy
Material and the sheath wall provider required by JSON BCs. Electron
energy initial *molar energy density* remains a separate `.i` parameter.

The potential variable must exist (or be generated by the separate Poisson
Physics). Required reaction rates, RF heating and other coupled physics
retain their own respective providers. The `physics_app/ci/`
`dd_plasma_boundary_json_physics_auto_p2.i` fixture uses
`solve=false` and `kernel_coverage_check=false`: native
`--check-input` validates object construction, **not** actual time
integration, missing lazy Functors or production scientific parity.

Historical source inputs and S6 production references remain immutable;
current scratch staging must not silently change their physics or provenance.
Only the active JSON + .i interface and synthetic P2 cases are migrated.

## 6. Evidence and release gates

- P0 canonical names, exact JSON/explicit-BC field equality, old
  factories absent, and source-identity-preserving S6 scratch migration.
- P1 native MOOSE/Physics application compilation.
- P2 native `physics-opt --check-input` on canonical JSON/explicit
  BC fixtures, malformed input negatives, ADParsed alternative, and
  Physics auto-state construction fixture.
- P3 **not run**: no powered time integration, sheath-particle/energy
  conservation equality, table lookup domain comparison, or accepted
  science parity.

**The old input source artifacts are reference evidence, not
compatibility registrations.** Do not mark runtime support as complete
until native P0/P1/P2 and required P3 independently succeed.
