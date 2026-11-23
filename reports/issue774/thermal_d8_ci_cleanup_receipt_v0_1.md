# #774 D8 — ThermalDiffusion legacy CI retirement and New-only separation

> **D8 CI cleanup: PASS within the checked source/CI scope.**
> **Old current-binary input support: NOT REQUIRED** by explicit requester decision.
> This is **not** a blanket safe-delete, science, external generated-caller, or main-merge approval.

## Verified immutable CI execution

- [Draft PR #791](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/791) exact HEAD `13b61931d06f176c73dfe4a6f939b89aa79a484b`.
- [Actions run #45192097120](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45192097120) **SUCCESS**; sanitized artifact **#14826972309**, ZIP SHA-256 `be7077872f156ae03ac4c65dc3a308b723be91292c1006eb26cf0472e563a863`.
- Original historical FDEG ZIP SHA-256 `57e49b50df16dbd690d2899384cf7fa048c01a6f6e6cb4ab59154f1717b414a0` checked successfully by `ci/guards/fdeg_thermal_archive.py`.

| Original FDEG P0 owner | Tests | Verdict |
|---|---:|---|
| Structural | 16 | PASS |
| Functional | 23 | PASS |
| Transition | 18 | PASS |
| Harness A-D (including D8 retirement and historical archive negatives) | 32 | PASS |
| Scan Cache | 10 | PASS |
| **Total** | **99** | **PASS, zero failures** |

## Actual CI cleanup, not just an issue comment

- Source/header `PhysicsFVThermalDiffusion.C/.h`: absent in tested source-cut branch. Active `.i`, C++ Physics source, workflows and relevant Python generators: **zero literal old-Factory references across 691 tracked active candidate files**.
- Active FDEG Functional/Transition profile sets: exactly **9**, same registered names, **9 source Blob SHA identities match**. Retired Thermal profile: **not active**. FDEG code7 historic source/policy is stored only in the immutable archive, with original graph mutation negatives retained.
- Physics Code CI original job and FDEG validation step count **unchanged**. No stale live source capture; **one pinned archive validator**, **one historical artifact upload**. The CI cleanup JSON receipt is now emitted by the existing archival step into the same existing artifact.
- Five exact path filters were added for both `push` and `pull_request`: two active FDEG profile JSONs, the D8 retirement CI contract JSON, the historical ZIP and its anchor. This closes the material gap where changing an archive/baseline alone did **not** launch the relevant validation.
- Negative controls require failure for: removed archive verifier, duplicated upload, old source-bound live capture, missing archive/registry CI trigger, active old `.i`/generator/Workflow reintroduction, modified surviving source SHA, policy waiver reversal, forged `safe_delete`, and modified archive digest.

The policy [issue comment #7103483022](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/774#issuecomment-7103483022) explicitly accepts **dropping old binary input compatibility**. It does **not** waive CI migration or the historical evidence integrity gate.

## Two CI histories must not be mixed blindly

The [New-only post-cut B #783](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/783) at `c77d2f773eee96c30eeca49d7486fea22ea8e557` has a separate exact Git tree `f6ef251777e89d9d9b4faca84d282a5425494f64` (1,703 tracked blobs). It contains **no old Thermal C/H, no `.github/workflows/physics-code-ci.yml` and no legacy FDEG Functional/Transition profile registries or historical FDEG archive verifier**. Its actual New-only CI is `.github/workflows/ci.yml`, plus the **branch-only** targeted D5 Native P05 source census. This is a separate ancestry and should not receive all historical FDEG/Physics Code CI files through an unreviewed cherry-pick.

The D5 [A #781](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/781) and [B #783](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/783) 417/941 complete P05 registered-source parity is already separately verified. D7 [#789](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/789) confirmed old-type binary interface break. D8 closes the **historical source-cut CI transition**, not New-only integration.

## Integration contract and holds

1. Keep #791 as an unmerged Draft and attach the **exact D8 artifact**. Do not merge to `main` during active Poisson work.
2. **Drop one-off D5/D6/D8 evidence workflows at final integration**; preserve original run IDs and artifacts. Do not introduce D8's historical Physics Code CI into the New-only branch without reconciling the current CI architecture.
3. Preserve nine remaining live FDEG profiles and pinned historic code7 evidence only in branches where they are still part of the normal CI authority. Keep D8's exact path triggers on that authority.
4. Any eventual combined merge candidate must requalify the exact HEAD against the authoritative CI contract. An existing Draft's green run does not transfer to a different combined tree.
5. Independent external/generated consumer scope, review/rollback and unrelated P3/P4 scientific acceptance are not asserted here. **`safe_to_delete=false`, `SCIENCE_HOLD`.**

**Verdict: `D8_FDEG_CI_CLEANUP=PASS / OLD_INPUT_SUPPORT=WAIVED / NEWONLY_CI=SEPARATE / MAIN_MERGE=DEFERRED`.** See [machine receipt](thermal_d8_ci_cleanup_receipt_v0_1.json).