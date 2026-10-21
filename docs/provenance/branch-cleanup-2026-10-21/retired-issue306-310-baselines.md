# Retirement of historical Issue #306 and #310 baseline branch refs

Date: 2026-10-21
Repository: `HyungseonSong-plasma/moose-test-repo`

## Operator decision

The operator explicitly requested permanent cleanup of these two former preservation exceptions and limited the present operation to **these two branch refs only**. This supersedes the `EXPLICIT_PRESERVE` disposition recorded by `docs/provenance/branch-cleanup-2026-10-08-round6-final/README.md` for these two names; the earlier archival decision remains historical evidence, not current live-branch policy.

| Branch ref authorized for deletion | Exact last observed head | Historical role | Historical issue |
| --- | --- | --- | --- |
| `issue-306-sequence08-baseline` | `1b28a1bccbec4ccad5e597500142a7e7e06ef4a3` | Sequence 08 heavy-charge / Gummel fixed-point ratio-4 comparison baseline; qualification claims bounded by tested horizon | [#306](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/306) (closed 2026-09-22) |
| `qualified/issue310-gummel-optimized` | `cdba1cba025da3c8442c0ad2993aeccab0111732` | Historic Gummel/MultiApp fixed-point cost optimization and solution-parity experiments; not a mandate to reactivate the older architecture | [#310](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/310) (closed 2026-09-25) |

Historical commit URLs (immutable commit identifiers, subject to GitHub's Git-object retention):
- [Issue #306 baseline commit](https://github.com/HyungseonSong-plasma/moose-test-repo/commit/1b28a1bccbec4ccad5e597500142a7e7e06ef4a3)
- [Issue #310 qualified-head commit](https://github.com/HyungseonSong-plasma/moose-test-repo/commit/cdba1cba025da3c8442c0ad2993aeccab0111732)

The closed Issues retain their source/evidence narratives. Deleting a branch ref does not rewrite historical commits, accepted numerical observations, evidence artifacts, or the meaning of previous qualification claims. These two old branch heads are no longer retained as active baselines.

## Scope exclusions

- **Do not change** `issue-280-sol-gateway-cutover` or [PR #303](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/303); its resolution is outside this operation.
- **Do not change** `experiment-full-fem-contour-mesh`, `main`, Issue #397 active experiment branches, or integration PRs #398/#399/#400.
- No Physics code, experiment, scientific result, or PR merge is changed by this branch cleanup.
- The only destructive actions are Samuel exact-SHA-guarded deletions of the two refs above; each must be verified absent afterward.

## Evidence limitations

A GitHub Actions query by either branch name on 2026-10-21 returned no workflow runs, which is **not** proof that the historical numerical evidence or cited earlier work never existed. Existing issue body records are retained unchanged. This provenance entry is sufficient to recover the operator decision and exact head names without requiring those branch pointers.
