# Retired Issue #397 integration PR branches — 2026-10-23

## Authorized branch-ref cleanup

After the successful PR integration sequence [#398](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/398) → [#399](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/399) → [#400](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/400), the operator requested branch cleanup. The three retired heads are superseded **in repository content** by their respective verified squash-merge commits on `main`. Deletion is limited to the three *remote branch refs*, with Samuel's exact-SHA branch-delete lease, not history editing, PR closure, CI alteration or physics refactoring.

| Branch ref | Exact head SHA before deletion | Merged PR | Main squash-merge SHA |
| --- | --- | --- | --- |
| `integrate/issue397-01-runtime` | `26294d08c05f99fa834c3fe29843ad48584f0151` | [#398](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/398) | `2fee276b5c3dbcdee1410fcaf1d42104bb47cd37` |
| `integrate/issue397-02-l1-baseline` | `a584ec16451dd4f56a388978d3a8cdc5d68b7f64` | [#399](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/399) | `2e14935e9bab03e684c4e01a35840d8e125802d9` |
| `integrate/issue397-03-power-scan` | `472ccd1a0871d60281289f8a1e99fc7cd9f00c61` | [#400](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/400) | `90820c5730b01d7e99be4e4673fff5f18eae4e48` |

## Verification and evidence

- All three PRs show `merged=true`, `state=closed`, and the exact merged commit listed above.
- [Issue #397](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/397) and [Issue #403](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/403) are closed. Their experimental runtime evidence is kept independently from PR branch deletion.
- PR #398: C++ PhysicsApp pinned-build test and head CI/SOL integration succeeded; retired optional Bohm/negative-ion barrier code was removed before merge.
- PR #399: re-stacked onto `main` before merge; canonical Graded Coarse L1 / native wafer D1 diagnostics included.
- PR #400: unauthorized permanent workflow explicitly **not merged**; Samuel-governed manifest and guarded one-shot *template* integrated instead. The final `main` push CI succeeded at `90820c5730b01d7e99be4e4673fff5f18eae4e48`.
- There were no in-progress Actions jobs at the time of verification for these three PR integration refs.
- Original PR head SHA may not be reachable from `main` after squash merge. The merged file contents, PR discussion, Actions records and this mapping are primary retained provenance; do not presume indefinitely retained unreachable Git objects.

## Explicitly retained branches

The following are **not** authorized for deletion in this pass because their own research/head provenance is not subsumed by the squash merges, or their work is active/separate:

- `main`
- `issue-280-sol-gateway-cutover`: open [PR #303](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/303)
- `feat/semantic-directory-role-guard`: unmerged directory-role guard work
- `experiment-full-fem-contour-mesh`: distinct legacy FEM-contour history
- `issue-397-l1-graded-coarse-baseline`
- `issue-397-l1-graded-power-scan-200-250-300w`
- `issue-397-maxwell-tolerance-300-400w-diagnostics`
- `issue-403-graded-l1-500-600-700w-power-up`
- `issue-403-graded-l1-800-900-1000w-final-scan`

The five experimental branches diverged from an older baseline and contain research workflow/experiment revisions not merged wholesale into `main`. Closing a physics issue is **not** by itself a reason to drop the last Git ref to unique experimental commits. Retire them only through a separate explicit provenance/archive review.

## Mutation contract

Mutation performed through `.github/workflows/samuel-branch-delete.yml` by updating only `automation/mutations/branch-delete-request.json` with the three exact `branch` and `expected_sha` pairs, then observing the Jobs to terminal status and verifying the target remote refs are absent. No destructive action on protected or unmerged branches is authorized by this record.
