# Retired Full FEM contour-mesh experimental branch — 2026-10-23

## Disposition and exact identity

At the operator's request, the historical branch `experiment-full-fem-contour-mesh` is **retired**: the selected plasma/wafer production mesh for Issue #397/#403 is now the Graded Coarse L1 baseline in `main` (1,739 nodes, 3,155 triangles, 27 wafer faces, mesh SHA256 `ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc`). The independent Full FEM contour-mesh numerical/mesh branch is not the accepted future baseline.

- Repository: `HyungseonSong-plasma/moose-test-repo`
- Retired branch: `experiment-full-fem-contour-mesh`
- **Exact terminal branch HEAD before deletion:** `acf4ad72eb3060d9cc5f3ecb5c9d763253926bbd`, 2026-10-09 (last commit message: `Merge PR #381: complete Issue 331 monolithic plasma discriminator`)
- Previously closed, unmerged [PR #363](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/363) proposed promoting an older hybrid FEM/FVM baseline; it was **not** accepted as `main`.
- Open PR #303 uses a *different* branch; `main`, `feat/semantic-directory-role-guard`, and `issue-280-sol-gateway-cutover` must remain untouched.

## Verified mainline mesh functionality

The contour mesh generator
`experiments/fem_fvm_plasma_discriminator/generate_contour_mesh.py`
is already present in `main` and is byte-identical to the generator on the retired branch (Git blob SHA `d7c2d8f7609dd5443bf9a4eccf0b5e31bff4e28a`). The **active** Graded Coarse L1 input/mesh implementation, however, comes from the independently reviewed Issue #397 integrations [#398](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/398), [#399](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/399), [#400](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/400). Retiring this branch does not disable any accepted mesh generator.

## Archive of historically unique source (inert text)

A fresh Git-tree comparison revealed that the branch was **more than a mesh generator**: approximately 190 original-branch paths not present in `main`, including 64 legacy GitHub Actions workflows and 16 CI triggers, plus 36 differing existing files. None of these differences is automatically accepted physics code.

The `source/` directory beneath this document preserves **24 selected unique Git blobs (80,800 bytes total)**, including:
- original contour `.msh` mesh and legacy full-FEM case-preparation scripts;
- hybrid ion transport, neutral-flow staging, and wall-layer-refinement preparers;
- experimental electron-impact O₂ dissociation coefficients and provenance;
- PhysicsApp source/header pairs for `PhysicsBoundaryLayerRefineGenerator`, `PhysicsFVLogMassFractionTransport`, `PhysicsElectronImpactDissociationMaterial`, `PhysicsTransferredSolutionPredictor`, `PhysicsCoarseP1ConstraintProblem`, `PhysicsFastFixedPointAdaptiveDT`, and `PhysicsVariableStateAudit`.

They were copied as **unchanged original blob SHAs** (not re-serialized/reformatted) and are stored with added `.txt` filename extensions so they do not compile or register as production PhysicsApp objects and cannot run as workflows. After commit `5d96f55c3469c63566c2228c7287381b8adc93d3`, the archive was independently verified to contain exactly 24 items, all with matching original branch blob SHA.

**Important limits:** This is *selective* archival, **not** a full Git bundle or whole-branch history preservation. The remaining historical workflows, CI triggers, legacy modified PhysicsApp files, and unselected experiment scripts are intentionally not integrated. The old commit HEAD is recorded for forensic reference, but GitHub may eventually prune unreachable commits after ref deletion. Therefore no future reconstruction of the entire historical branch is guaranteed from the commit SHA alone.

## Historical experimental run links

The original GitHub Actions runtime records provide the bounded scientific history:
- [run #37776427672](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/37776427672) — Full FEM on three-level contour mesh, completed success;
- [run #37777911329](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/37777911329) — Full FEM contour mesh 300-step run, completed success;
- [run #37783791866](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/37783791866) — ion-only FVM hybrid on contour mesh, completed success;
- [run #37786627342](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/37786627342) — ion-only hybrid staged dt, completed success.

These histories are diagnostic experiments on an older numerical configuration. They do **not** supersede the selected Graded L1 / EI17 mesh and 100 µs results, nor are old CI successes proof that the archived components remain buildable or suitable on today's `main`.

## Mutation scope and verification

Only the remote branch ref `experiment-full-fem-contour-mesh` is authorized for deletion. Samuel's pre-existing `.github/workflows/samuel-branch-delete.yml` must receive the exact head SHA `acf4ad72eb3060d9cc5f3ecb5c9d763253926bbd` in `automation/mutations/branch-delete-request.json`. Verify the workflow's terminal matrix success and individual GitHub 404 for the deleted ref. Mainline physics, the active mesh, PID, chemistry, other branches and PR states must not change.

Deletion verification: **PENDING**.
