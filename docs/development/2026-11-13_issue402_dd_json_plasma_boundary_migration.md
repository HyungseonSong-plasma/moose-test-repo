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

## 2. ElectronEnergyMaterial.C: one output, two different input states

Canonical registered class:
`physics_app/src/materials/ElectronEnergyMaterial.C`.
The former `PhysicsElectronMeanEnergyMaterial.C` class and file are
**deleted**. The unique Material output is the AD Functor
`e_energy_eV` [mean electron energy, eV per electron].
The previous `mean_en_solved` output alias, configurable
`mean_energy_output` option and *this Material's* `normalized` state
mode / `energy_reference_eV` parameter have been deleted.

Supported state forms are genuinely distinct:

- `log_molar_eV` (default): the two input Functors contain
  `log_e_energy` and `log_e` [logs of molar energy density and
  electron molar number density]. The material evaluates
  `e_energy_eV = exp(log_e_energy - log_e)`.
- `physical_eV`: two physical Functors contain actual electron
  energy density `U_e` [eV/m3] and number density `n_e`
  [1/m3]. It evaluates `e_energy_eV = U_e / n_e`.

The modes cannot be silently unified because the input units and numerical
state representations differ. The original AD expression and finite/nonzero
guards are kept for both surviving modes.

A no-new-physics option is an explicitly provided
`ADParsedFunctorMaterial` defining
`property_name=e_energy_eV`,
`functor_names='log_e_energy log_e'` and
`expression='exp(ue-un)'`. Its `--check-input` PASS checks
object construction only, NOT equivalent AD Jacobian or fail-fast
invalid-state behavior.

```ini
[FunctorMaterials]
  [electron_mean_energy]
    type = ElectronEnergyMaterial
    state_form = log_molar_eV
    electron_energy_density = log_e_energy
    electron_density = log_e
  []
[]
```

The DD lookup owner in `DDTransportMaterial.C` now directly reads the
`e_energy_eV` Functor. The JSON lookup coordinate remains implicit.

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
`physics_app/src/physics/plasma/Chemistry.C` registers these BCs during
MOOSE `add_bc`. Electron mean-energy and wall flux FunctorMaterials
remain explicit `[FunctorMaterials]` inputs; JSON BC declarations
do not implicitly instantiate them.

## 5. Can JSON + one MOOSE .i drive electron equations?

**Yes for explicitly complete MOOSE input, not yet for a minimal
Energy Physics declaration.** `DDEnergyEq.C` currently binds/creates
`log_e_energy` and its initial condition and attaches selected RF
heating and Chemistry energy source Kernels. It does **not** generate
the complete time-derivative/drift/diffusion electron energy
operators. Mean-energy and wall-flux FunctorMaterials, mesh,
potential, additional physical kernels, source Functors, constraints,
and the relevant BCs must still have their actual owners.

`dd_plasma_boundary_json_physics_auto_p2.i` is a construction-only
test that asks Physics to auto-create `log_e` and
`log_e_energy` from JSON + MOOSE `.i`, and wires the JSON-specified
electron BCs and explicit Materials. `solve=false`: a passing
`--check-input` is *not* evidence of a complete simulated electron
energy equation or its physical correctness.

Historical S6 production additionally uses archived input layers,
rate/transport providers, electric field/RF operators and their
original reaction-progress source definitions. An Issue #402 scratch
preparer is still needed to reproduce that staged system from
historical sources. Deleting that preparer without replacing these
owners would be a silent physics regression.

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
