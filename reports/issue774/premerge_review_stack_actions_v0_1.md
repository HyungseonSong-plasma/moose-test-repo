# #774 — pre-merge technical review and dependency/CI reconciliation (2026-11-23)

> **Status: technical review completed; independently approved review NOT received. Merge to `main` remains HOLD.** This document does not modify production physics, workflow, Poisson, or the successful test-only validation source.

## Verified current refs and actual scope

| Branch/PR | Immutable head / state | Meaning |
|---|---|---|
| `main` | `156a5117ebe6816e67b352a9470572c2e74da367` | Current protected integration baseline; still tracks `PhysicsFVThermalDiffusion.C` |
| [#665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) | `9457191f4c0693ae886586edd961965867ccd5c0`; Draft, base `main`, HOLD | Upstream S6 ion_2 FV/ion_3 C2 integration prerequisite |
| [#783](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/783) | `c77d2f773eee96c30eeca49d7486fea22ea8e557`; Draft | Actual old Physics Thermal `.C/.h` source removal on New-only after #781 |
| [#793](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/793) | `87b7d97113ce6e75081dd15c56c86bc159bde6c9`; Draft | Permanent New-only retirement CI Guard/test |
| [#807](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/807) | `51475b5eeb2e40c9f71bac30012daa7954e3b3b7`; Draft, base #793 | **Clean production candidate**, no new production Jobs |
| [#808](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/808) | `edbdcf2ea4867e7fcbee4a0e40b6780f1acf2a06`; Draft | **Test only**: 1 validation Workflow + 4 scripts/tests, do not merge |
| [#813](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/813) | Reports-only Draft | Evidence and pre-merge report; no production edit |

GitHub comparison confirms `#665` head is **an ancestor** of #807, with #807 **18 commits ahead / 0 behind** and just 10 net file changes from #665 (including the actual Thermal source deletion). A direct comparison of `main` and #807 gives **322 ahead / 156 behind**, **125 changed files**; this is **large branch divergence, not a proven textual merge conflict**. Canonical `ci.yml` on `main` is 11,382 bytes; on #807 the byte-identical canonical CI/template pair is 176,001 bytes. Thus **do not cherry-pick Thermal deletion or retarget #807 to main as if it were an isolated two-file change**.

## CI and Actions hygiene — confirmed

On #807 exact Git tree `aa5e033fe836bf51bf18761cd32041d2818e2fed`: **39 tracked workflow YAML files**, **zero `.github/workflows/issue774*` one-off files**, **zero historical `physics-code-ci.yml` or `physics-native-ci.yml`**. Existing canonical `.github/workflows/ci.yml` and `ci/workflow_templates/general-ci.yml` have the **same Git blob SHA `bfc17426006315c0b64dfb1e6add0a949b1183b0`**. D5/D9 branch-only Workflows were deleted from the clean production tree. D10–D14 and #808 validation-only Workflows are intentionally outside #807; preserve their historical runs and SHA-pinned artifacts, but do not merge these temporary CI files.

[Run #45219450397](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45219450397) executed **all 3 sequential jobs successfully** at the #808 exact SHA whose only differences from #807 are five temporary test files: W1 single compile PASS, 417/941 actual Native P05 PASS (77 events each, 16/16 expected negatives, 44/44 D10 parity), and Public D 100-row Native P2 PASS (8/8 actual `Syntax OK`, all 22 original public stage files preserved, two authorized changes plus one new JSON). The P05 and PublicD jobs used the **same exact W1 ELF** and verified private scratch cleanup.

**Important limitation:** #808 ran the D14 standalone stage verifier and D9 source CI guard, but **did not run the entire 176KB canonical production `ci.yml`** on a final `main`-targeted merge SHA. The newly added inline canonical `PUBLIC_D_COMPLETE_SUPPORT_DELTA_PASS` assertion has been inspected and covered by equivalent D14 stage behavior, **not yet by execution of that exact inline Python snippet as part of the canonical production CI job**. Do not convert source/marker P0 PASS into full canonical CI PASS.

## Concurrent change lines — conflict-risk inventory

| PR/branch | Observed overlap | Integration treatment |
|---|---|---|
| [#810](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/810), banded electron correction retirement | Forked from **D9**, not #807; independently changes the same `ci/guards/issue774_newonly_fvkernel_retirement.py` and two FVKernel retirement test modules; deletes different Physics `.C/.h`; introduces two branch-only Workflows | **Rebase/replay onto accepted #807 or later stack; reconcile one central guard and drop its temporary Actions; rerun scoped Native** |
| [#812](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/812), heavy-mass correction retirement | Directly stacked on **#807**, changes the same retirement guard and tests, deletes another distinct Physics `.C/.h` | **Can review after #807; separate source-retirement approval and exact-head test** |
| Active Poisson G6B public-100 parallel branch `26e84a4a33cf93d9e278a4f0b2d78c53cae2d6ce` | Compared with #807 **60 ahead / 18 behind**. Changes PhysicsApp Poisson/chemistry and its own case/workflow runtime; canonical CI blob SHA `543de1708171f3bf9052f46c0baf927f14fd1c65` (not #807's `bfc174...`); `issue774_newonly_fvkernel_retirement.py` absent at that head | **Preserve Poisson independent history and reconcile both CI/template/retirement contracts in a future integrated branch; do not auto-merge or mark its P3/P4 full-time results PASS on #807** |
| `main` | Still has old Physics thermal `.C` and smaller original CI; #665 is unmerged | **Accept/requalify #665 separately before attempting full New-only stack promotion** |

This table records actual **overlapping file paths and ancestry**, **not** proven Git textual conflicts, not PR approvals, and not a request to combine unrelated science changes prematurely.

## Technical review observations and required gates

1. **P0 release blocker — integration base:** #665 remains Draft/HOLD on `main`. Final stacked merge must preserve its S6 contract and the post-cut New-only source/CI chain (#781 → #783 → #793 → #807), without importing D8 historical FDEG or temporary D5–D14 validation Actions. Main-targeting combined exact SHA must run the authoritative source/CI checks and applicable runtime gates. Do not mark #774 closed before actual stack promotion.
2. **P0 release blocker — independent review:** #807 currently has **0 submitted independent reviews**. This document is an automated technical review/triage, **not** a second person's or external model's approval. Require an actual reviewer or explicit owner release disposition; do not self-attest as independent.
3. **P1 release blocker — canonical production CI execution:** The newly added inline Public D complete-stage assertion and full workflow/template generation must run at the final merged SHA, not only equivalent D14 standalone Python and a marker-count self-test. In particular the full input stage must still yield exactly 22 original public files with only two modified old files plus one generated JSON, and private artifacts must remain excluded.
4. **P2 hardening — fail-closed symlink handling:** The new inline `public_manifest()` uses `if p.is_file() and not p.is_symlink()`, which silently **skips** newly introduced file symlinks instead of rejecting them. A local minimal reproduction confirmed the manifest stays unchanged when a file symlink is added. The stricter D14 standalone verifier already rejects symlinks. Amend both byte-equal canonical CI and template to explicitly fail on symlinks (and add a negative regression) before production promotion. This is a review finding **not yet patched in #807**, so the validated #807 source head and successful #808 proof remain immutable.
5. **P1 related PR/Actions hygiene:** #810 and #812 modify the same central retirement guard/tests; review their removals separately. Reconcile their guard changes only after an accepted base, drop all branch-only Workflows in the production end-state, and close stale PRs/issues/branches only after retaining immutable evidence and confirming final integrated replacement.
6. **Science boundary:** P2 `--check-input` does **not** establish P3/P4 100-µs numerical conservation or Poisson semantic compatibility. Preserve these as separate physics release gates where required; do not manufacture successful runs.
7. **External users:** Requester says there are generally no external consumers and old typed input compatibility need not be maintained. `KNOWN_EXTERNAL_INTEGRATIONS=NONE_REPORTED` (not proof of universal zero); no outside caller-zero investigation or imaginary owner signoff release gate. `QPXFVThermalDiffusion` belongs to a separate Application and is untouched.

## Recommended exact promotion sequence (no merge performed)

- **A — Upstream:** resolve #665 independent S6 base acceptance and test its main-target exact merge SHA, or explicitly retain HOLD.
- **B — Thermal stack:** integrate pre-cut source-census ancestry #781, actual C++ removal #783, permanent New-only guard/CI #793, clean CI integration #807 in order; squash/replay as appropriate but **exclude temporary validation workflows and test-only #808**. Preserve D8 FDEG separately.
- **C — Siblings:** independently validate #812 (already on #807), then rebase #810's different source-removal line to the accepted head; reconcile shared guard/tests, re-run their actual Native tests. Coordinate G6B Poisson and `physics_harness/workflow` contract migration as a distinct merge with its own CI and P3/P4 gates.
- **D — Closure:** test *the final combined source SHA*, inspect generated Workflow/template byte equality, all remaining permanent guard/tests, actual 417/941 input construction, protected scratch cleanup, archived rollback and independent owner/reviewer decision. Only then consider `main` merge, historical PR/issue closure and branch/workflow cleanup.

**Current status: `CLEAN_PRODUCTION_CANDIDATE_VERIFIED_IN_ISOLATION / MAIN_BASE=HOLD_665 / POISSON_BRANCH=DIVERGED / INDEPENDENT_REVIEW=NONE / CANONICAL_COMBINED_MAIN_CI=NOT_RUN / SAFE_MAIN_MERGE=HOLD`.**
