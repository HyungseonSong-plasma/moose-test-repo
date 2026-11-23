# #774 D6 — Thermal FVKernel consumer and compatibility review

> **D6 static classification verified; independent consumer/compatibility closure HOLD.** No original Physics source or Poisson change in this report-only branch; no merge to `main`.

## Exact execution and provenance

- D6 audited **Draft PR #786** exact head `a0c325e0fd7f1d871a60f4f179dfea71ddaf1413`, [run #45183621897](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45183621897), artifact #14822027558.
- Source artifact ZIP SHA-256: `cec9510f30586fda973a4833da4148ff99b924e6faf87c8d613c293eed2d1d32`. Inventory SHA-256: `0c9e8deaf904e3b5baa89d865aeeea98380aba126255d6e2b5f89466b3cd3e80`.
- D6 fail-closed P0: **5 consumer-audit tests + 26 FDEG/archival tests PASS**. Actual `GitSourceProvider → run_scan()`: **900 selected, 698 scanned, 202 unresolved files, 1,766 unresolved items; PARTIAL / UNVERIFIED; zero source-verification failures**.
- 84,706 nodes / 258,019 edges / 258,919 source-bound evidence records. Graph completeness is relative to the selected collectors, not global compatibility or consumer closure.

## Exactly observed tracked-source references

Audited **1,804 tracked paths** at the immutable Git commit, with two binary/nonregular paths excluded from text searching. All plain-text **exact token** references to `PhysicsFVThermalDiffusion` or the separate `QPXFVThermalDiffusion` were classified; no worktree fallback.

| Reference class | Paths | Concrete disposition |
|---|---:|---|
| Live direct PhysicsApp `.i` type references | **0** | None found **within tracked literal source**; generated and external paths are still unverified |
| Literal direct target generator/script references | **0** | None found; unknown dynamic strings cannot be treated as caller-zero |
| FDEG test and guard references | 5 | **KEEP_ACTIVE_GUARD**; preserved archive, graph mutation negatives and independent review gates |
| Historical reports/development documentation | 8 | **ARCHIVE_HISTORICAL / REVIEW_BLOB**; never treat docs as a live `.i` just because a line says `type = ...` |
| Separate QPX thermal diffusion type | 4 | **KEEP_UNCHANGED_OTHER_APP**; historical Issue20 input, preparation and associated evidence |

No active `ci/baselines/fdeg_*` profile for the retired class remains in the **Draft #777 cut rehearsal**. Its original, exact pre-cut graph is preserved byte-for-byte in [archive Draft #776](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/776). The original `PhysicsFVThermalDiffusion.C/.h` are absent **only on the rehearsal stack**, not `main`.

Important: this is a **literal tracked-source census**, not a complete dynamic/generated warehouse consumer inventory. The separate D5 exact-head Native A/B in [#781](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/781) and [#783](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/783) established equal **417/941 P05 FVKernel registrations and 16/16 negative controls each**, including **0 Thermal registrations in A**. D5 does not extend this scope to old inputs or 100-us P3/P4.

## Current-binary compatibility contract is not automatically discharged

The removed kernel computes `-D_T * grad(T).n / T` with explicit ON/OFF, face interpolation and boundary handling. `NVTransportMaterial` or `PhysicsThermalDiffusionMaterial` can publish coefficients but does **not** establish an equivalent FV residual owner. The Issue20 `QPXFVThermalDiffusion` is a **different Factory**, not an alias.

Three possible owner decisions, none silently assumed:

1. **Keep legacy compatibility:** preserve this Factory implementation in a current-binary mode; no permanent C/H removal while old input support is required.
2. **Archive-only support:** explicitly approve the loss of current-binary legacy input compatibility, retain a runnable historical source/binary/input environment and its exact receipt, and supply an independent compatibility decision and rollback plan.
3. **Semantic replacement:** add a supported replacement with independent nonzero-gradient, internal/boundary flux, ON/OFF, units/sign and AD residual checks. A successful build or zero-gradient smoke is insufficient.

## Static evidence false positives: repaired but never silently waived

Draft #786 extends `verify_retired()` with **optional** exact-path, exact Git Blob SHA-1 verification for reported evidence under `reports/issue774/*.json/.md`; a separate `independent_metadata_review_ref` is required. No blanket `reports/` exclusion and no retrospective modification of the frozen pre-cut `historical_protected_blobs`. Synthetic tests prove that missing review, modified report blobs, executable extensions, and newly reintroduced `.i` consumers still cause HOLD. **No authentic independent review or approval was supplied in this PR.**

## D6 closure gates remaining

- **External/generated:** independently attest the exact historical and external input consumer universe; source scan and API interposer alone do not close it.
- **Current-binary compatibility:** owner-selected legacy support policy with a pinned runnable archive or independently verified replacement. Current decision **UNAPPROVED**.
- **Independent receipts:** coverage, Native/semantic if needed, current binary decision, metadata review and rollback review; do not invent references.
- **Integration:** New-only [#665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) and active Poisson work remain unmerged. Keep this D6 stack separate.
- **Scientific acceptance:** 100-us P3/P4 and global residual/AD equivalence remain `SCIENCE_HOLD`.

**Status: `D6_STATIC_TEXT_SOURCE_CENSUS_VERIFIED / D6_COMPATIBILITY_AND_EXTERNAL_CLOSURE_HOLD / SAFE_DELETE=HOLD`.** See sibling [machine receipt](thermal_d6_consumer_compatibility_v0_1.json).