# #774 D5 — New-only FVKernel Native P05 A/B evidence (2026-11-23)

> **Verified: PASS_SCOPE_ONLY_NOT_DELETION_APPROVAL.** Evidence-only branch; do not merge to `main` or interpret as external caller-zero, scientific equivalence or a file-removal authorization. Poisson G1–G5 work is deliberately excluded.

## Immutable evidence

| Cohort | PR / source SHA | W1 | Native P05 | Sanitized artifact |
|---|---|---|---|---|
| A, source intact | [#781](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/781) `6c4eef073038ad69a0710e7c8555b5e03b9ad6ba` | PASS | [#45177303119](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45177303119) PASS | #14820526285 |
| B, Thermal .C/.h absent | [#783](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/783) `c77d2f773eee96c30eeca49d7486fea22ea8e557` | PASS | [#45177755891](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45177755891) PASS | #14818699271 |

Both use exact, independently built ELF hashes and the same pinned OCI. Both 417 and 941 have 11-layer source input SHA, Chemistry JSON SHA and mesh SHA matching between A/B. The 16 intended Native negative rejections passed in **each** cohort; the protected scratch was verified removed, with no private rate data or raw object names published. Original `12+12+8` New-only owner uniqueness checks are preserved.

## Observed source census (per 417 or 941)

- **13 source files / 18 PhysicsApp Factory type registrations in A; 12 / 17 in B.** B removes only `PhysicsFVThermalDiffusion.C` and its header from Physics source, preserving the remaining source blob identities.
- Each case produced **77 post-original-call registration events**: **40 FVKernel, 21 FVBC, 16 FEM BC**. All family counts, type-by-type FVKernel counts, framework/other type counts and 12+12+8 owner checks match between A/B.
- Existing source-owned FVKernel registrations observed per case: New-only `FVLogMolarTransport.C` **9**; conservative mass-fraction accumulation **3**; heavy mass-fraction advection **3**; mixture-averaged diffusion **3**; species reaction sources **6**. Framework/other FVKernel types account for the remaining 16 registrations.
- All **eight** provisional old-source candidates in #774 were **0 observed in this instrumented P2 API**. In particular, **`PhysicsFVThermalDiffusion.C` A=0**, and its only source/header are absent in B. This is **run-scoped non-observation**, not proof that all eight are unused globally.
- The tracer records multiple loader constructor markers (**417: 323 each; 941: 309 each**). The D5 parser now requires marker presence rather than exactly one, while retaining raw trace SHA, event counts and original registration uniqueness.

## Required remaining D6 gates

1. **Full consumer disposition:** per-source active, Python-generated, legacy replay, external/dynamic and CI consumers; supported historical modes cannot be assumed removable.
2. **FDEG/thermal compatibility:** original [archive PR #776](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/776), [source-cut simulation #777](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/777), live CI/profile transition, explicit current-binary legacy support decision and independently signed archive/coverage/native/rollback receipts.
3. **Stacked New-only integration:** upstream [#665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) remains unmerged. No direct main merge, no Poisson file or JSON changes. Requalify against accepted integration base when available.
4. **Science:** 100 µs P3/P4 and scientific/AD residual parity not established; keep `SCIENCE_HOLD`.

Machine-readable receipt: [newonly_d5_verified_ab_p05_v0_1.json](newonly_d5_verified_ab_p05_v0_1.json). This report preserves only public sanitized evidence identities and verdicts. **`deletion_approved=false`, `safe_to_delete=false`.**
