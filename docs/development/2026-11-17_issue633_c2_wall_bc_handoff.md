# Issue #633 / C2 — Ion Wall Material & FV Boundary Handoff

**Status:** SOURCE IMPLEMENTED / P0 TESTS PENDING EXACT HEAD / P1–P3 HOLD. This document does not authorize Native deletion.

## Current single-head schema (supersedes the original ion_3 handoff)

As of the single-integrator PR #665, the **run-facing JSON has no species.ion_wall object**.
Wall physical parameters are flat species fields:
`wall_molar_mass`, `wall_sticking`, `wall_ion_temperature_eV`, and
`wall_use_element_gradient_for_potential`. The unchanged wall-law values
are 0.032/0.016 kg/mol, sticking=1, ion-temperature=0 eV, and FEM
element gradient=true. Migration-gate smoothing is NOT JSON-owned.

The wall's number-density and mobility Functors are derived from species ID,
`<id>_number_density` and `<id>_mobility`; potential and block are read
from `[Physics]/[Plasmas]/[Transport]/[DriftDiffusion]/[Continuity]`
(`fem_potential`, `block`). Gas-temperature Functor is exactly
`temperature`, published by the root `[Plasmas]` MOOSE input alongside
`pressure`. No independent `T_g_fixed` provider is created by C2.
The old `ion_wall` JSON object is explicitly rejected by the parser.
The migrated numerical gate is specified **once per Continuity instance**
in the MOOSE `.i` input, not once per species:
```ini
[Physics]
  [Plasmas]
    pressure = 1.333223684
    temperature = 300
    [Transport]
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fvm_species = 'O2p Om Op'
          fem_potential = potential
          migration_smoothing_width = 0.001
        []
      []
    []
  []
[]
```
The `[Continuity]` option is now **optional** with a default of `0.0` V/m.
Both an omitted option and explicit `migration_smoothing_width = 0`
select the exact hard outward-only `max(z E_n,0)` gate. Positive widths
preserve the existing tanh smoothing calculation. Negative or nonfinite
values are rejected. The historical S6 C2 characterization uses an
**explicit** `0.001 V/m` in the New-only S6-417/941 templates to avoid
silently changing that scenario's numerical behavior.
The parser rejects `migration_smoothing_width` and retired
`wall_migration_gate_smoothing_width` anywhere in mechanism JSON.
The lower-level existing `IonWallFluxMaterial` factory still accepts
`migration_gate_smoothing_width` internally to preserve historical
Native inputs; the new `[Continuity]` option maps into that factory
parameter without introducing a second user-facing JSON owner.
Two new **non-executable until Scratch is staged** review fragments
`issue633_newonly_s6_{417,941}_continuity.template.i` record the
S6-specific `.i` placement. They do not constitute P2 evidence.

This modifies only the active new-only integration candidate. Historical
S6 source inputs and the separate hybrid recipe are immutable. Validation
is still P0 source-level until exact-head Native build and P2 prove the path.

## Integration boundary

- Implementation branch: `issue-633-c2-on-ion2-20261117`; stacked on [ion_2 PR #661](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/661).
- [C2 PR #663](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/663) modifies **only** `Chemistry.C/.h`, C2 material/BC factories, an opt-in JSON overlay, Python guards and tests.
- `DDContinuityEq.C/.h` are ion_2-owned. C2 reads its `fvm_species` selection using `ActionWarehouse::getActions<Plasma::DDContinuityEq>()`; no second discretization/owner switch exists.
- C2 explicitly adopts ion_2 donor factory sources `IonWallFluxMaterial` and `FVLogMolarDielectricFluxBC`; the wall law and dielectric sign formula were not altered.

## How C2 is activated

Provide the new `physics_app/ci/issue633_c2_wall_3ion_overlay.json` **after** the resolved S6-417/941 chemistry mechanism file(s), and select `fvm_species = 'O2p Om Op'` with an explicit `fem_potential = potential`.

The overlay supplies only flat species `wall_*` metadata, `ion_surface_current.electron_wall_number_flux` and 4 physical `boundaries` groups with 12 ion FVBC objects. It does not introduce an additional `fvm_kernel_ownership` flag. The root parser allows only one JSON `boundaries` owner: integrate any existing electron FEM BC definitions into the same root `boundaries` object rather than adding competing root owners.

The selected species must match configured `ion_wall` producers exactly. The parser rejects duplicate/missing producer records, non-finite or nonphysical numeric inputs, swapped mobility/density names, wrong potential, species/variable/flux mixing, factor sign, unsupported FV BC types, overlapping/missing sidesets and incomplete BC cardinality.

| Species | Generated Material | General Neumann BC | Dielectric BCs |
|---|---|---|---|
| O2p | `O2p_wall` → `O2p_wall_number_flux` | `O2p_wall` (FVBC) | `O2p_cover_dielectric`, `O2p_wafer_dielectric`, `O2p_focus_ring_dielectric` |
| Om | `Om_wall` → `Om_wall_number_flux` | `Om_wall` (FVBC) | `Om_cover_dielectric`, `Om_wafer_dielectric`, `Om_focus_ring_dielectric` |
| Op | `Op_wall` → `Op_wall_number_flux` | `Op_wall` (FVBC) | `Op_cover_dielectric`, `Op_wafer_dielectric`, `Op_focus_ring_dielectric` |

The general `FVFunctorNeumannBC` uses `-1.6605390671738466e-24` on `inlet outlet plasma_electrode plasma_metal plasma_right`. The 9 dielectric FVBCs use `FVLogMolarDielectricFluxBC` with `signed_number_flux` on `plasma_cover`, `plasma_wafer`, `plasma_focus_ring`; their C++ residual uses **`gamma_signed / N_A`**, not the Neumann negative factor.

Three `ADParsedFunctorMaterial` outputs preserve `cover_net_surface_current_density`, `wafer_net_surface_current_density`, `focus_ring_net_surface_current_density` and expression `1.602176634e-19*(gi+gop-gm-ge)`. Current `DDEnergyEq` generates `ESWallFluxMaterial` without `species_id=e`, publishing **`electron_wall_number_flux`**, not `e_wall_number_flux`; this is the explicitly selected consumer in the overlay. The electron producer is created only when the electron sheath BC path is active — its reachability is not established by this overlay alone.

## Upstream and downstream ownership

The C2 wall materials consume `O2p/Om/Op_number_density` and `O2p/Om/Op_mobility`. No new number-density provider is created by C2: ion_1/P09 must establish unique live solver-to-density and coefficient producer chains. The `carrier_one` drift and `T_g_fixed` gas-temperature inputs also require verified upstream owners in the new-only scratch assembly.

**ion_5 Scratch cutover MUST address three different classes of old owners**:
1. The 26 Native ion FV Kernel/BC objects (14 Kernel + 12 BC), using their post-transform exact block receipts;
2. The three historical Native ion wall Material declarations, **additional** to those 26;
3. The three old `cover/wafer/focus_ring_surface_current` Material producers, because C2 intentionally now generates Functors with the same published output names. Never delete these without independently checking every surface-charge consumer and exact target owner; retain historical archived sources unchanged.

P05/ion_2 must prove runtime warehouse uniqueness for 12 FV Kernels and 12 FV BCs at one executable HEAD. C2's static JSON proof cannot replace that check. A success under `--check-input` is P2 construction only, not a physical P3 acceptance.

## Test commands

```bash
python3 -m pytest -q tests/test_issue633_c2_wall_bc_contract.py tests/test_issue633_c2_json_wiring.py
python3 ci/guards/issue633_c2_json_wiring.py --json physics_app/ci/issue633_c2_wall_3ion_overlay.json
python3 ci/guards/issue633_c2_wall_bc_contract.py --mode native-provenance --input experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i
```

These commands establish only local P0/static contracts. Exact-HEAD CI source/test evidence, a real `physics-opt` P1 build, both S6-417/941 new-only P2, post-scratch 24/24 warehouse/owner ledger and eventually 400 W / 100 µs P3 are separate gates. **SCIENCE_HOLD and P1_NATIVE_CUTOVER=HOLD** until explicit release.
