# Issue #402 — DDMaterial / NVMaterial source ownership

**Status:** code prepared in Draft PR #523, P1/P2 and scientific parity independently gated.
Do not execute P3, merge, or accept S6 source equivalence solely because a
MOOSE `--check-input` succeeds. `SCIENCE_HOLD` is unchanged.

## Ownership

| Model | Canonical C++ type and filenames | Coefficients / units |
|---|---|---|
| DriftDiffusion | `DDMaterial.h/.C` | `<species>_mobility` [m²/(V·s)] and `<species>_diffusivity` [m²/s] |
| NavierStokes (heavy species) | `NVMaterial.h/.C` | `D_mix_<species>` [m²/s], `D_T_<species>` [kg/(m·s)], `kT_<species>` [−] |

`DDMaterial` is one FunctorMaterial per species. It **only** produces
mobility/diffusivity coefficients. `model=constant` requires explicitly
specified, finite, nonnegative physical `mobility` and `diffusivity`;
no fallback coefficient is inferred. `model=lookup` loads the same
three-column `PhysicsLookupTable1D` and AD linear interpolation previously
used for electron transport. Specify exactly one lookup file and one
coordinate Functor. `table_units=reduced` divides table values by
`N_n=p/(k_B T_g)`; `table_units=physical` uses table values directly
for other species. An electron DD owner also publishes the established
`electron_*` output names and Maxwellian `5/3` energy mobility/diffusion
projections from **the same** particle coefficients.

`NVMaterial` is a direct class/file rename of
`PhysicsThermalDiffusionMaterial`. The existing binary collision data,
Chapman–Enskog, thermal diffusion, heavy mixture diffusion and dynamic
Debye–Hückel charged-pair evaluations remain unchanged. In this revision
the new source, after reverting the class rename and historical MOOSE alias
registration line, is **byte-identical** to the pre-refactor implementation.
`NavierStokes` transport should consume it, not an electron lookup.
Mixture-derived `D_mix` must not be substituted for a DD ion diffusivity
without a separate model/units verification.

## Example new input (not a validated physics parameter set)

```ini
[FunctorMaterials]
  [electrons]
    type = DDMaterial
    species_id = e
    model = lookup
    table_file = electron_transport.txt
    coordinate = mean_en_solved
    table_units = reduced
    pressure = p
    gas_temperature = T_g
  []
  [positive_ion]
    type = DDMaterial
    species_id = O2p
    model = constant
    mobility = 0.1
    diffusivity = 0.01
  []
  [mixture]
    type = NVMaterial
    temperature = T_g
    pressure = p
    transport_data_file = heavy_transport.txt
    species = 'O2 O'
    mass_fractions = 'w_O2 w_O'
  []
[]
```

The numeric constants above illustrate syntax only; never use them as an
accepted S6 rate, ion transport closure, or production input.

## Deleted implementations and preserved semantics

- **Deleted** `ElectronTransportLookupMaterial.h/.C`: its reduced lookup,
  bounds handling, species/electron outputs and electron energy factor moved
  into `DDMaterial`. Historical MOOSE `type=ElectronTransportLookupMaterial`
  and `type=PhysicsElectronTransportLookupMaterial` are **factory aliases**
  of the new C++ class, not duplicate implementations.
- **Deleted** `PhysicsThermalDiffusionMaterial.h/.C`: replaced by
  `NVMaterial.h/.C`. The historical MOOSE type name is accepted as a
  factory alias. Heavy numerical formulas have not been edited.
- **Deleted** `PhysicsElectronTransportCoefficients.h/.C`: older ADMaterial
  electron transport coefficients, with no reference found outside its own
  .h/.C in repository code search. Do not reintroduce a second owner.
- **Deleted** `ElectronClosureMaterial.h/.C`: this previously duplicated
  electron mean-energy + table lookup. The direct native Material smoke now
  obtains mean energy from the existing `PhysicsElectronMeanEnergyMaterial`
  (state bridge), `electron_temperature_K` from a dimensionally identical
  parsed derived Functor, and transport coefficients from `DDMaterial`.
  This *old combined factory name is intentionally retired*, rather than
  maintained as a second coefficient-calculation implementation.
- **Previously retired** `PlasmaClosuresAction`,
  `PhysicsElectronKineticsMaterial` and `PhysicsHeavyTransportMaterial`
  remain absent; `PlasmaMechanism` and `ChemistryPhysics` are already
  consolidated into `Chemistry`.

**Not deleted (still required):**

- `PhysicsElectronMeanEnergyMaterial`: computes the electronic state
  coordinate; is not a mobility/diffusivity Material.
- `SpeciesTransportAliasMaterial`: short-term, **only** for live ion
  coefficient Functors in historical S6 / FVM inputs, whose values are not
  constant and not guaranteed to match a standalone lookup. It passes AD
  values through without coefficient recomputation. Remove only after
  identifying real `DDMaterial` provider equivalents and proving transport
  parity, including signed charge and units.
- `PlasmaChargeTransportMaterial`: charged mass-flux and drift assembly,
  not merely coefficient lookup. The redundant `ion_charges` option remains
  a future JSON charge-authority migration and cannot be deleted as a
  harmless refactor.
- `PhysicsElectronImpactRateMaterial` and `PhysicsReactionRateMaterial`:
  Chemistry rate producers, not transport coefficient calculators.

## Verification requirements

1. Source-check that both new C++ classes are the sole canonical coefficient
   calculator classes and all retired source/header paths are absent.
2. Native P1 compile, check `physics_app/ci/dd_nv_material_smoke.i`
   (electron constant, O2p physical 1D lookup, NV heavy collision model),
   and run legacy electron reduced lookup smoke using the old factory alias.
3. For the actual scientific workflow, numerically compare `mu,D` and
   `D_mix,D_T,kT` at representative states/boundaries, including charged
   collisions, lookup bounds, AD derivatives and the energy `5/3` factor.
4. Confirm no double coefficient owners or altered charge/material scaling,
   and run a separate S6-417/941 P2 + source-parity gate. Until then,
   **P3 and merge stay disallowed**.

**Compatibility note:** old MOOSE type tokens for the two renamed transport
implementations are retained only because historical executable input
depends on them. The retired combined `ElectronClosureMaterial` is **not**
aliased: dependent source tests and the direct smoke were migrated to two
independent responsibilities.
