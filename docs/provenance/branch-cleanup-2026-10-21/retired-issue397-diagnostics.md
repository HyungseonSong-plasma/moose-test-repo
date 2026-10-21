# Retired Issue #397 diagnostic branches — 2026-10-21

## Disposition and scope

Operator decision (2026-10-21):
- The Bohm ion wall-boundary alternative is abandoned; do **not** promote it to the accepted physics baseline.
- The operator considers the prior wafer checkerboard problem addressed by selection of the canonical **Graded Coarse L1** numerical baseline.
- The isolated N1/S1 normal-current-sign diagnostic and the separate Case 2 center-wafer r<=20 mm mesh-refinement lane require no further review.
- This record authorizes retirement of three diagnostic **branch refs**, not deletion or rewriting of historical GitHub Actions evidence and not a claim that numerical mesh resolution proves a universally correct physical sheath model.
- No physics code, Bohm BC, or diagnostic-only probe code from the three branches is integrated into `main` by this cleanup.

## Retired heads (immutable provenance)

| Remote branch to delete | Exact head SHA | Meaning | Recorded execution |
| --- | --- | --- | --- |
| `issue395-wafer-interface-normal-current-sign-n1-s1` | `51da598367452da50498251a4ae8d9405558da10` | Isolated N1/S1 plasma normal and wall-current sign control, fixture, auxiliary native probe | [run 39330670648](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39330670648), completed success (bounded isolated control only) |
| `issue-397-case2-wafer-r20mm-mesh-levels` | `8a0c81f815e527283404fc82c461f2c408ba31a6` | Separate Bohm Case 2 center-wafer local L1/L2/L3 refinement/discriminator | [run 39561542021](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39561542021) cited in Issue #397; not accessible through current workflow-run API at cleanup, so no terminal result asserted |
| `issue-397-case3-bohm-positive-thermal-minus-100us` | `77f2d7b93f6328afc66255711bc60c629a146649` | Bohm positive-ion wafer alternative with O-minus restored to thermal+migration; **physics option rejected for future use** | [run 39503471011](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39503471011), completed success (solver/audit, not physical acceptance) |

## Canonical surviving baseline and controls

- Graded Coarse L1: 27 wafer faces, 1,739 nodes, 3,155 2D triangles, mesh SHA256 `ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc`.
- Baseline branch `issue-397-l1-graded-coarse-baseline` stays while [PR #399](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/399) is open.
- Power-scan branch `issue-397-l1-graded-power-scan-200-250-300w` stays while [run 39617859962](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39617859962) is in progress; integration PRs [#398](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/398), [#399](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/399), [#400](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/400) stay.
- Baseline original thermal+migration ion-wall BC is unchanged. The user-directed conclusion about operational resolution does not upgrade pending P3/P4 results or establish independent scientific root-cause proof.

## Preservation rule

Branch pointers may be deleted using Samuel's exact-SHA, live-ref/readback-verified branch-delete workflow. Commit IDs, issue history, past Actions URLs and this decision record are preserved. Old runs may expire independently of the Git branch refs; this record is not a complete archive of binary evidence.
