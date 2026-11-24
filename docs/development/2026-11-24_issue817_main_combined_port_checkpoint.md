# #774 / #817 — latest-main combined retirement port checkpoint

Status: **ARCHIVAL_PREPARATION_ONLY; NOT MERGE READY**. No new active C/H cut in this checkpoint.

Base main: `0755571b5d011f89a7473704337e23c042273381`; base candidate #823: `19b6fa4c6a8e964cfa80674d8b6daa267f52fafc`.
Qualified isolated New-only #807: `c70d4b65c530b3d80f104b14d5a91daae5179f50`, exact tree `267b8599ea8fce147200e3da8c3f06e6f71f7ffb`, direct CI #45352240783 5/5 PASS. Different ancestry; never merge its 329-ahead/163-behind stack into main wholesale.

## Frozen evidence

Six original Code1/2/3 source/header blobs are copied verbatim under docs/development/archive/issue774_retired_factories (existing Thermal/Heavy archives retained):

- `FVElectronResponseBandedCorrection.C.txt`: `1e58703a7794ddd8eed3cba28ed9e5a1e39a141f`
- `FVElectronResponseBandedCorrection.h.txt`: `9446a9d5d7863fb83a2c65af8b127bbd08573ad6`
- `PhysicsFVElectronEnergyJouleHeating.C.txt`: `07ecd234871c659b04389c87bff6f52fae7f800e`
- `PhysicsFVElectronEnergyJouleHeating.h.txt`: `1d2afa9ba448041c664fdc1822ede5472b93551e`
- `PhysicsFVElectronReactionSource.C.txt`: `35ded0eab65ad7bed85baa0104261c90bc26bf3d`
- `PhysicsFVElectronReactionSource.h.txt`: `5250b3500d6694481158e2abb896c7e1c6f349e9`

Seven exact evidence/lineage blobs from #807 retained:

- `ci/baselines/fdeg_historical_profiles_code1.json`: `9a8b0d60a9511fe089ef6cb3d900f902123ee742`
- `docs/development/issue809_code1_newonly_retirement.md`: `ba9ea289d6d3fdf880fd78bc40f02b4336aac45b`
- `docs/development/issue814_code2_heavy_integration.md`: `6b740286fbf946a761fcde0718d312497a5e1a99`
- `docs/development/issue817_code3_production_migration_receipt.md`: `4cf185f60180c1588f50d62f391f6c978a0de63c`
- `docs/development/issue817_code3_source_cut_candidate.md`: `3961470da450bf848d6a4802329bf516fc69b0f3`
- `docs/provenance/issue814_code2/electron_energy_joule_smoke.i.txt`: `6c4901f843a98b74b450cc3a1fab09e8e1873b2c`
- `docs/provenance/issue817_code3/issue192_s5r_pre_migration.py.txt`: `be9838b77dc2920b27a1f7065648062b630eacb5`

## Collision-free Code3 migration map

All 12 destination preimage blobs were directly matched to pre-combined #807 `78e22f617c81e45cd64bfa10f4959d83bb3a3dcb`. Port in an atomic cutover after main-specific FDEG/guard reconciliation. Do not apply by filename alone if base moves.

| Path | Required old blob | Qualified replacement blob |
|---|---|---|
| `experiments/Issue224_standard_source_projector_memory/run.py` | `e3cd38318ab3d31ab0f374009c2845f0d1a46f41` | `13d5b5619211f8c775f0f955de91f989287003a1` |
| `experiments/historical_recipe_support/issue192_s5r.py` | `be9838b77dc2920b27a1f7065648062b630eacb5` | `7dc29e5773b145d9f052d9898901eec61c904344` |
| `physics_app/ci/check_e8_ei16_energy_runtime.py` | `be2b570b98a4c72951c3b3c3436c798a6a6e4279` | `14bc739c45a89c2e1ce3040fcf4a3e208038dddc` |
| `physics_app/ci/check_issue402_json_rate_native_p2.py` | `edf242a66e45133126ef5276e359199a31f490ab` | `a3af595afe0e104156dd8c6c75ca1f8cc38e8f7c` |
| `physics_app/ci/check_r2_o2_ionization_implementation.py` | `5aeb469c21ed11dcb193d85a34c598eaa8788637` | `202dcad4ba693806f7c4fab199c9404c42e88a40` |
| `physics_app/ci/check_stage5_edetach_runtime.py` | `58529f67d3ecd907f6188cfbd4bdb5334ff93c66` | `2cf58fec130f93d9c07d4a9e2b5405ce490d24b6` |
| `physics_app/ci/check_stage5_ei20_runtime.py` | `74fd8f4afbade4b60a1de4822d23b6841239e6a1` | `d7de7edd0095032247845824740f8e3dbf7e70cf` |
| `physics_app/ci/check_stage5_h05_runtime.py` | `9be80ecc037b5db46d9de91aa6ce546440bb557e` | `dc1debca2f59373d1adec2148611d632563bbdad` |
| `physics_app/ci/check_stage5_s5r_preflight.py` | `47ddc6729aa15da0bd19726d1dacecdef7f1ae9b` | `ca3e7a0daefc85841274e144ea53a5e362f0002f` |
| `physics_app/ci/check_standard_moose_energy_projection.py` | `f5c2a9666956d6f7eac3c96502c764e6d05577d1` | `9debb80a88ecc488b623759cc1e9d4dce51b2cee` |
| `physics_app/ci/ei01_attachment_runtime_smoke.i` | `86f411b220466bd719189cfba411cf4391549495` | `0c2f05c1d7292aafeaa15955d87943e65c7e2f01` |
| `tests/characterization/test_issue192_s5r.py` | `857517add40b7b2cfff3ff73ed9d85a2434833bf` | `938088ac7e1fd09b8696c31a3e584db05f994705` |

## Remaining main-specific work (not performed here)

1. Preserve all ten original FDEG functional/transition profiles and their source witnesses. Main Physics Code CI currently captures live Code3. Change live capture to a retained profiled Factory after confirming its actual graph; migrate retired-target tests to exact pinned historical fixtures, including Code1/2/3, without dropping assertions. Check structural virtual-instance expectations and historical generated-input blobs against pinned pre-cut snapshots.
2. Extend main retirement guard (not the incompatible New-only guard wholesale): five retired names / ten original C/H blobs, 8 C / 13 Factory, exact historical S5-R preimage and migrated lineage, narrow negative/provenance assertion classification, original Joule smoke archive, current consumer and absence controls; retain split CI and ARCH owners. Port verified Code3 guard/test and migration map, recompute census tests. Inspect all changed main paths and modes before C/H removal.
3. Run canonical main Repository CI, Physics Code FDEG suites, retained FLOW/ARCH and split P6 W1/417/941/Public D, bounded Code3 Native on exact candidate. Prior #807 results cannot substitute for new main HEAD. Do not change Poisson scope or protected inputs.
4. Full representative S5-R/AD, scientific P3/P4 and historical/external compatibility acceptance remain HOLD. Main and #823 unchanged; do not close #774/#809/#817 or delete prior evidence branches.

This checkpoint adds archival/provenance files only; no active implementation, canonical workflows, existing FDEG profile registries or production branch changed.
