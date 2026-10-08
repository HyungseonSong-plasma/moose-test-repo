# Branch cleanup provenance — round 6 final

Date: 2026-10-08

## Result

Final remote branch count: **7**.

Final preserved branches:

- `main`
- `experiment-full-fem-contour-mesh`
- `issue-280-sol-gateway-cutover`
- `issue-306-sequence08-baseline`
- `qualified/issue310-gummel-optimized`
- `issue331-stageb-monolithic-charged`
- `issue-331-governed-compile-manifest`

## Reviewed obsolete branches removed

- `experiment-local-h-refine-2237`
- `experiment-strict-fv-cell-charge`
- `experiment-wall-cell-average-subgrid-run`
- `experiment-wall-refinement-level-matrix`
- `experiment-wall-temperature-subgrid`
- `experiment-wall-temperature-subgrid-run`
- `issue-gen34-parity-inspect`
- `mean-energy-primary-state`
- `recover-qualified-plasma-inputs-20260927`

Operational cleanup branches removed after merge:

- `ops/branch-cleanup-round6-final-20261008`
- `ops/samuel-branch-delete-gateway-20261008`
- `ops/fix-samuel-branch-delete-pin-20261008`

## Samuel branch-delete capability

The final cleanup used the central Samuel exact-SHA branch-delete action pinned to:

`HyungseonSong-plasma/chatgpt-operation@7705024f3b150c986d851be67bf36298be200e7e`

The mutation contract is:

1. reject deletion of `main`;
2. require an exact lowercase 40-hex expected branch-head SHA;
3. fresh-read the branch through GitHub Git Ref API;
4. hard-stop on stale SHA;
5. delete through the GitHub Git Ref delete endpoint;
6. read back the ref and require absence;
7. treat a branch that was already absent before mutation as `NO_MUTATION_NEEDED`.

The first gateway execution failed closed because the initial Samuel implementation used GitHub's singular `/git/ref/...` endpoint for DELETE. The post-delete readback detected that the branch still existed, so the cleanup did not silently claim success. Samuel was corrected to use singular `/git/ref/...` for reads and plural `/git/refs/...` for deletion; endpoint sequencing is now pinned by central tests.

The corrected 11-target batch passed for all targets, followed by a final exact-SHA deletion of the last staging branch. A fresh remote inventory then contained exactly the seven preserved branches listed above.
