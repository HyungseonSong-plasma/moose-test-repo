# Issue #633 — S6 New-only electron, energy and pressure ownership handoff

Status: **P0 source inventory and fail-closed preflight contract; real 11-layer
Scratch and native `physics-opt --check-input` remain HOLD. No CI or P3 started
by this change.** The historical S6-417/941 archive and Hybrid inputs are immutable.

Evidence sources:

- `experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i`
- `experiments/Issue402_plasma_dsl_g1/issue633_newonly_s6_{417,941}_continuity.template.i`
- `experiments/Issue402_plasma_dsl_g1/chemistry/unified_s6_{417,941}_newonly.json`
- `physics_app/src/physics/plasma/DDContinuityEq.C`
- `physics_app/src/physics/plasma/DDEnergyEq.C`
- `physics_app/src/materials/DDTransportMaterial.C`
- `ci/p1_ion_new_only_preflight.py`, checked by
  `tests/test_issue633_s6_energy_owner_cutover.py`

## Specific original-owner to generated-owner decisions

| Legacy S6 owner / interface | New-only owner / canonical name | Scratch-only required step |
|---|---|---|
| `[Variables]/log_ne`, `[Kernels]/ne_time` | `DDContinuityEq.fem_species=e` -> `log_e`, its FEM Time/Transport and Chemistry Source | Retire Native electron solver variable and overlapping electron kernels; rewrite all remaining `log_ne` consumer references to `log_e` |
| `[Variables]/log_energy`, `energy_time`, `energy_transport`, `energy_joule` | `DDEnergyEq.fem_species=e`, `fem_potential=potential`, `transport_coefficient=fluid` -> `log_e_energy`, FEM Time/Transport/Joule and Chemistry Energy Source | Retire Native energy variable, Time, Transport, Joule and overlapping source kernels; rewrite consumers to `log_e_energy` |
| `[FunctorMaterials]/mean_energy` (`PhysicsElectronMeanEnergyMaterial`), Functor `mean_en_solved` | `DDEnergyEq::addFunctorMaterials` -> `ElectronEnergyMaterial`, `e_energy_eV` | Retire old Material; remap old consumers from `mean_en_solved` to `e_energy_eV` |
| `[FunctorMaterials]/electron_transport` (`PhysicsElectronTransportLookupMaterial`) | JSON `species.e.transport_coef.type=lookup` -> `DDTransportMaterial`, `e_mobility`, `e_diffusivity`, `electron_mobility`, `electron_diffusion`, and 5/3 energy aliases | Retire explicit lookup Material so two producers cannot publish the same mobility/diffusion aliases. Table and clamp bounds are retained |
| `[FunctorMaterials]/electron_physical_density`, Functor `n_e_physical` | `DDEnergyEq::addFunctorMaterials` derives `n_e_physical` from `log_e` | Retire old density producer; preserved Poisson/RF consumers use the unchanged Functor name |
| `[FunctorMaterials]/electron_wall_flux`, Functor `electron_wall_number_flux` | Full `DDEnergyEq` creates `ESWallFluxMaterial(species_id=e)` -> `e_wall_number_flux` | Retire the old electron wall producer; rename the consumers to `e_wall_number_flux` |
| Native 4 electron + 4 electron-energy FEM BC objects | New JSON grouped `FEMElectronSheathBC` and `FEMElectronEnergySheathBC` (same 8 physical sideset-owner groupings) | Retire all 8 old FEM BC residual objects. Keep the two C++ types separate |
| Native `cover/wafer/focus_ring_surface_current` Materials | C2 Physics produces same `*_net_surface_current_density` properties using new wall Fluxes | Retire old current producers; **keep** `PhysicsLowerDSurfaceCurrent` Kernel and surface-charge/Poisson equations |
| `[Variables]/p` (`INSFVPressureVariable`) and all `pressure=p`, `variable=p`, `functor_names='p ...'` consumers | Same solved `INSFVPressureVariable` renamed **`pressure`**; `[Plasmas] pressure=1.333223684` creates sole `FVConstantIC` and live `pressure` FV Functor | Rename solver variable and **all** neutral/Rhie–Chow/pressure BC and EOS dependencies. Remove old `[pressure] initial_condition` so only one IC exists. Never replace the solved pressure with a fixed Functor |
| Native ion mobility/diffusion constants `10`, `0.25851999786435537` for all O2p/Om/Op | New JSON `transport_coef={type:constant,unit:physical,file:none,mobility:10,diffusivity:0.25851999786435537}` -> canonical Species coefficient Functors | Native coefficient *consumer* dependencies are retired with original ion Kernel/Wall owners. Old unrelated constant-name providers may remain temporarily but must not republish canonical `<species>_mobility/diffusivity` |
| Native `log_ni/log_nm/log_nop` | `DDContinuityEq.fvm_species='O2p Om Op'` -> `log_O2p/log_Om/log_Op` | Retire 14 Native FV Kernels + 12 FV BCs and old FV variables/ICs; retain Poisson/RF by remapping density-consumer producer expressions, without duplicating canonical density Functors |

## Initial-condition exactness

Original base initial FEM log states:

- `log_ne = -20.216123548032986`, i.e. `n_{e0} ~= 1e15` particles/m³
- `log_energy = -18.829829186913098`, giving `mean energy = 4 eV`
- `[Variables]/p initial_condition = 1.333223684` Pa

New JSON `e.initial_number_density = 1000000000000001.6` and
`e.temperature_eV = 8/3` yield
`log_e_energy = ln(1.5 * temperature_eV * n_{e0} / N_A)`,
numerically matching the archived energy IC. The `[Plasmas] pressure`
initial condition is the archived pressure, while the underlying pressure
remains a solved FV variable.

## New-only MOOSE Energy contract

```ini
[Physics]
  [Plasmas]
    files = 'chemistry/unified_s6_417_newonly.json'
    pressure = 1.333223684
    temperature = 300
    wall_gradient = adjacent_element
    [Transport]
      [Chemistry]
        block = plasma
      []
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fem_species = e
          fvm_species = 'O2p Om Op'
          fem_potential = potential
          migration_smoothing_width = 0.001
        []
        [Energy]
          block = plasma
          fem_species = e
          fem_potential = potential
          transport_coefficient = fluid
        []
      []
    []
  []
[]
```

The mechanism JSON no longer contains `species.e.energy_transport_coef`.
For existing legacy flat schema only, the historical reader retains the field
as backwards-compatible metadata, but **new-only C++ generation derives
fluid energy ownership exclusively from `[Energy]`**.

## Mandatory gates before claiming handoff success

1. Reconstruct both S6-417 and S6-941 **disposable 11-layer Scratch** cases
   with pinned original SHA evidence; inspect all ten historical layers, not
   only the shared base layer.
2. Use owner-aware deletion of Native FEM/FV equations, electron wall/lookup/
   mean-energy/physical-density Materials and duplicate electron BC/current
   producers. Do not delete Poisson, RF, neutral-flow or lower-D charge
   consumers. Rewrite all old references including pressure `p`; retain
   the physical solver family, block and initial values.
3. Run `ci/p1_ion_new_only_preflight.py --contract new-only` on both staged
   11-layer cases. The guard checks *full* Energy, fluid selector, single
   solved pressure owner without duplicate IC, retired log/e/p aliases,
   duplicate electron kernels/materials/BCs, Native ion FV owners, duplicate
   generated coefficient Functors, and current producer collisions.
4. Run the actual target `physics-opt --check-input` (P2) on the exact
   integrated HEAD. **No P1/P2 runtime PASS is claimed by this review.**
5. Explicit P3 approval remains a separate gate; no long S6 execution was
   launched as part of this schema/ownership revision.

Both C++ source and static tests have been updated on Draft PR #665 using
`[skip ci]` commits. This document is an owner-inventory and acceptance
contract, not a record of a successful S6 simulation.
