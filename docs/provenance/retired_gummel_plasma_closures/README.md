# Retired GummelIteration / PlasmaClosures fixtures

Historical evidence only. These files are exact-byte snapshots of the source paths at `de51d59d250cac730f24b4a5937c531d27c1e233` after R1/R2 integration. The GummelIteration and PlasmaClosures Actions are no longer registered on main; these decks and the old #351 pressure-comparison runner are not current runtime inputs. The original paths are deliberately inactive. For historical replay, check out the appropriate qualified historical revision and its matching executable and dependencies; do not interpret these snapshots as compatible with current PhysicsApp. See `physics_app/docs/qualified_migration_2026-09-27.md` and historical evidence run 36163219902.

Shared transport/rate tables remain in their original locations because active direct Material fixtures and other inputs reference them. The separately pinned Issue351_frozen_heavy_driver_parity runner is not part of this change.

| Original path (under this directory with .txt suffix) | Git blob SHA |
|---|---|
| `physics_app/ci/plasma_closures_smoke.i` | `99c9a88404398e48f194685c2b4b1ff39b56aca2` |
| `physics_app/ci/gummel_plasma_closures_driver.i` | `25100d6e14bc6dd0f31b8b5f0c0d3273b5cd7319` |
| `physics_app/ci/gummel_plasma_closures_heavy_electron.i` | `aeeb853fcbee4893f6250939923c4d583742ddc0` |
| `physics_app/ci/gummel_plasma_closures_heavy_main.i` | `d2b1317a89bc1a9c2c839f144f6f4f4c77acd186` |
| `physics_app/ci/gummel_plasma_closures_heavy_poisson.i` | `82b8a02ca622aebd1b5f3dd1e429476b1ed56386` |
| `physics_app/ci/gummel_action_smoke.i` | `50b153c490363408ecff1414d86f52cb25c6868f` |
| `physics_app/ci/gummel_action_poisson.i` | `14cfe02839a49775c9964ea0d5a414dd3d662db4` |
| `physics_app/ci/gummel_two_subapps_main.i` | `690e11bb8c161c3f59234c89dbff8f334e8f81aa` |
| `physics_app/ci/gummel_two_subapps_electron.i` | `a90fce2edea9d628a173df606b84cecfa5eeb2f8` |
| `physics_app/ci/gummel_two_subapps_poisson.i` | `f1a447f24e91067b2f38097740526af058928770` |
| `experiments/Issue351_10mtorr_fixture/control.py` | `069dab040dd1e157c313bd32c7535fef75bb0857` |

The existing retirement checker guards exact archive identity and original-path absence. This archive is not evidence of external caller zero, full solver parity, or a physical model change.
