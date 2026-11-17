# Issue #633 / C2 — Ion Wall Material & FV Boundary Handoff

**Status:** SOURCE IMPLEMENTED / P0 TESTS PENDING EXACT HEAD / P1–P3 HOLD. This document does not authorize Native deletion.

## Integration boundary

- Implementation branch: `issue-633-c2-on-ion2-20261117`; stacked on [ion_2 PR #661](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/661).
- [C2 PR #663](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/663) modifies **only** `Chemistry.C/.h`, C2 material/BC factories, an opt-in JSON overlay, Python guards and tests.
- `DDContinuityEq.C/.h` are ion_2-owned. C2 reads its `fvm_species` selection using `ActionWarehouse::getActions<Plasma::DDContinuityEq>()`; no second discretization/owner switch exists.
- C2 explicitly adopts ion_2 donor factory sources `IonWallFluxMaterial` and `FVLogMolarDielectricFluxBC`; the wall law and dielectric sign formula were not altered.

## How C2 is activated

Provide the new `physics_app/ci/issue633_c2_wall_3ion_overlay.json` **after** the resolved S6-417/941 chemistry mechanism file(s), and select `fvm_species = 'O2p Om Op'` with an explicit `fem_potential = potential`.

The overlay supplies only additional species `ion_wall` metadata, `ion_surface_current.electron_wall_number_flux` and 4 physical `boundaries` groups with 12 ion FVBC objects. The C2 P0 guard also accepts a pre-existing `FEMElectronSheathBC` and `FEMElectronEnergySheathBC` within the same physical sideset group, while continuing to enforce unique FV BC operators. Order of the five ordinary wall sideset names does not affect ownership. It does not introduce an additional `fvm_kernel_ownership` flag. The root parser allows only one JSON `boundaries` owner: integrate any existing electron FEM BC definitions into the same root `boundaries` object rather than adding competing root owners.

The selected species must match configured `ion_wall` producers exactly. The parser rejects duplicate/missing producer records, non-finite or nonphysical numeric inputs, swapped mobility/density names, wrong potential, species/variable/flux mixing, factor sign, unsupported FV BC types, overlapping/missing sidesets and incomplete BC cardinality.

| Species | Generated Material | General Neumann BC | Dielectric BCs |
|---|---|---|---|
| O2p | `O2p_wall` → `O2p_wall_number_flux` | `O2p_wall` (FVBC) | `O2p_cover_dielectric`, `O2p_wafer_dielectric`, `O2p_focus_ring_dielectric` |
| Om | `Om_wall` → `Om_wall_number_flux` | `Om_wall` (FVBC) | `Om_cover_dielectric`, `Om_wafer_dielectric`, `Om_focus_ring_dielectric` |
| Op | `Op_wall` → `Op_wall_number_flux` | `Op_wall` (FVBC) | `Op_cover_dielectric`, `Op_wafer_dielectric`, `Op_focus_ring_dielectric` |

The general `FVFunctorNeumannBC` uses `-1.6605390671738466e-24` on `inlet outlet plasma_electrode plasma_metal plasma_right`. The 9 dielectric FVBCs use `FVLogMolarDielectricFluxBC` with `signed_number_flux` on `plasma_cover`, `plasma_wafer`, `plasma_focus_ring`; their C++ residual uses **`gamma_signed / N_A`**, not the Neumann negative factor.

Three `ADParsedFunctorMaterial` outputs preserve `cover_net_surface_current_density`, `wafer_net_surface_current_density`, `focus_ring_net_surface_current_density` and expression `1.602176634e-19*(gi+gop-gm-ge)`. Current `DDEnergyEq` generates `ESWallFluxMaterial` without `species_id=e`, publishing **`electron_wall_number_flux`** only when an electron sheath FEM boundary is present; the shipped overlay explicitly selects that name. Separately, `prepare_s6_run_input.py::canonicalize_staged_wall_inputs` can publish **`e_wall_number_flux`** from a verified scratch electron Wall source. C2 accepts *only those two explicitly selected names* and never silently aliases them. For the assembled Scratch input, choose **one actually existing producer** and verify no duplicate; the overlay alone does not establish either one.

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

## Integration audit 2026-11-17

- Exact source audit of PR #663 post-rebase: 51 checks PASS at C2 head `c92a30e213138a7f529839592f4fc4b4ee9d7878` (**source JSON/registrations only**, not a Python pytest/Native execution receipt). Includes wall count 3, normal FV BC 3, dielectric FV BC 9, 3 current producers and sign/factor/Functor wiring.
- Unity fix source HEAD `07e9369bd85cb8c82d2428abe0615af58f54e2c9` verified [FLOW P1 build PASS](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44053693905). The same run fails the historical S6-417 **D-base P2** input stage, not the compiler. This older P1 PASS does **not** promote post-rebase C2 binary.
- ion_2 exact source base `901e1c26a2ceed8898539241d278336ab0e68a18`; C2 branch was rebased with a SHA-guarded move, retaining 12 C2-owned changed files and no DDContinuityEq edits.
- ion_2 P05 warehouse check currently permits `bc_count == 0`. This must become strictly 4 per selected ion when C2 is active before P18/P25.

