# P6-X/C3 single-writer review, Runner/Owner contract and CI identity

**Date:** 2026-11-18  
**Scope:** Evidence and owner-mode boundary; not P6-X final PASS, scientific acceptance, a merge approval, or authorization to run P3/P4.

## Source identity and C3 decision

- Integration PR [#665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) observed at `3b447b67283dac3b1d5e592ed3db6e56754c3d0e`, parent `52067302d16074592503d0ef6b903cc344f55a08`.
- PR [#688](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/688) candidate `20f89959567a472180032683b38af5c920089825`; its four CI code blobs were included **exactly** in the #665 integration commit, with no Physics/P05 changes in that commit.
- `.github/workflows/ci.yml` and `ci/workflow_templates/general-ci.yml`: identical Git blob `24a2b278c3bd33649cb2c83be33e7abb2febd4eb`.
- `ci/guards/p6_ci_workflow_safety_guard.py`: `045f0e2d248247e23f601854d75a518bafe7af08`; test blob `457211dc1b68faa1a0679bca526f003beec9416c`.
- **C3 verdict:** `CONDITIONALLY_ACCEPTED_INTEGRATED_CODE`, not a global green CI or science result. Previous #688 run [#44345972609](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44345972609): validate 1,569 passed/13 skipped; 21/21 fail-closed negative mutations; four canonical and four old first-attempt Artifact names, 103/103 member bytes SHA parity; two independent Native lanes remained FAIL.
- **Artifact contract:** new `run_id-run_attempt-head_sha` name every attempt, old name only on first attempt, same bounded file paths, `if-no-files-found: error`, no legacy alias overwrite on rerun. Off-platform Artifact consumer compatibility remains **UNKNOWN**.
- `P05` remains fail-closed; no `dont_create_kernels`, `continue-on-error`, workflow skip, or auto-start P3/P4 or 150/200-step science.

## Independent Runner/Owner frozen decision

| Lane | Runner/Owner contract | Disposition |
| --- | --- | --- |
| Historical Public B | Pinned 10-layer reference in original-compatible PhysicsApp, Native P2 only, with original input SHA and archived executable. Not modern New-only or science equivalence. | `HISTORICAL_REFERENCE_PASS_ONLY` |
| Public D | Run independently per 417/941 from original **100-row** electron Lookup in disposable 11-layer Scratch under new Physics, with exact source/OCI/mesh SHA. Retire four manual e/O2p/Om/Op Transport producers; 14 old FV Kernels +12 old FV BCs → **0** only in authorized Scratch. Exactly one generated Transport/Chemistry owner for each e/ion; real seven species/eight case-specific reactions, signed `S_O2p_molar/S_Om_molar/S_Op_molar`; require actual generated **12 FV Kernel +12 FV BC +8 electron FEM BC**, P05 unique inventory, 5/3 electron energy/wall/current/Poisson preserved. Original 100-row SHA `994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387` stays distinct from prepared 42-row SHA `35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b`. Source-only P0 [#44351706480](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44351706480): 14 tests PASS, **NOT** 100-row Native. Isolated 42-row pilot P2 PASS does not prove 100-row. No historical Public D compatibility runner is newly authorized. | `KEEP_HOLD` |
| FLOW | Historical Hybrid 26 Native ion owners remain as immutable reference and `KEEP_HOLD`; never mix with 12+12 generated owners. Only separately authorized New-only Scratch retires old 26→0 with real P4-X producer cutover and modern generated Chemistry, 12 FVKernel+12 FVBC. 417 failed in [#44345972623](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44345972623); PR684 both-case P05 collision evidence [#44314726088](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44314726088) is not modern FLOW PASS. | `KEEP_HOLD` |
| ARCH Hybrid | Pinned historical 100-row compatible Native P2 receipt is archival only. Current modern S6-417/941 fails P05 on `log_O2p`: `ni_time [PhysicsFVLogMolarElectronTimeDerivative]`. Preserve the failure; no legacy 14+12 ion-owner overlap with generated 12+12, no skip, P05 waiver or synthetic success. A new Hybrid mode requires separate semantic/Owner approval and two-case exact-HEAD P2 evidence. | `KEEP_HOLD` |
| New-only | P5-X single ELF `912b212c3c1849165ab3da13d758f5b3e101f5b6cb7e1e3f3820259f6080f7eb` and 2 app libraries passed 417/941 P2, 32/32 typed registrations per case, 16/16 N1-N8 on exact **old** `52067302...` [#44347074110](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44347074110). New #665 `3b447b...` changes only C3 code, but strict latest-HEAD executable identity must be re-pinned or explicitly dispositioned; the older build is not a new exact-head receipt. | `PASS_52067302_ONLY / LATEST_HEAD_PIN_HOLD` |
| Legacy Ion-FVM | Independent physical contract and approved non-time-stepping P0/P2 only. No automatic 1/5/10 ns science. | `KEEP_HOLD` |

## New exact-head integrated CI

- Repository CI [#44352429008](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44352429008).
- FLOW [#44352428960](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44352428960).
- Both were independently **already auto-triggered** as `pull_request` on #665 `3b447b...`; do not dispatch a duplicate workflow.
- This contract was drafted while the new CI was running. Final status is determined from the terminal run/job readback, not inferred from PR #688's previous run.
- Do not convert known Public D/FLOW/ARCH failures to green. `P6_X_FINAL=HOLD` until independent Lane PASS or explicit approved operational KEEP_HOLD disposition and the required CI acceptance contract. `P7_FINAL=HOLD` pending P6-X.
- `SCIENCE_HOLD`, `Native P3/P4=NOT_RUN`, PR #665 OPEN/DRAFT, main unmerged, PR #684 unmerged. No private EI rates in artifacts.

This receipt is on an isolated evidence branch so it does not change the integration HEAD or trigger another expensive Native run.

## P6-X exact-HEAD integrated CI terminal audit — P6X-CI-3B447-TERMINAL

- [Repository CI #44352429008](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44352429008), `pull_request` attempt 1, exact head `3b447b67283dac3b1d5e592ed3db6e56754c3d0e`: **COMPLETED / FAILURE**, **15/17 jobs SUCCESS, two failures**.
- `validate`: SUCCESS, **1,569 pytest passed / 13 skipped**, source-only **21/21** intentional guard mutations rejected. C3 Workflow/template bytes and artifact guards accepted for this exact source.
- `plasma_native_regression`: P0 PASS, P1 source-bound build PASS; historical Public B 417/941 P2 `exit0/Syntax OK`. Public D 417/941 P2 `exit1` on **`Missing drift-diffusion transport JSON record for FEM species 'e'`**. **PUBLIC_D=KEEP_HOLD**, this is not physics/science FAIL.
- `issue541_arch_s6_hybrid_native_p2`: 417 and 941 both real Native `DDContinuityEq::checkIntegrity()` P05 collision on `log_O2p`: `ni_time [PhysicsFVLogMolarElectronTimeDerivative]`; both `exit1`. **ARCH_HYBRID=KEEP_HOLD**, not waived, not false-green.
- [Independent FLOW #44352428960](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44352428960): **COMPLETED / FAILURE** at `P2_S6_417_CHECK_INPUT_FAILED` after successful source and fixture checks; **FLOW_HYBRID=KEEP_HOLD**. Do not claim a 941 positive from a runner that stopped at 417.
- Actual first-attempt Artifact names were uploaded for CORE Four, Plasma Regression, ARCH DD, ARCH S6 Hybrid: **4 canonical + 4 legacy ZIPs**. All **103/103 inner members** match by independently recomputed SHA-256, all **8 CRC checks PASS**. ZIP archive digests themselves differ and do not replace member-byte identity. Canonical names encode `44352429008-1-3b447b...`; legacy names remain for attempt 1 only.
- Final scope: **`P6_C3_CODE_AND_ARTIFACT=PASS`, `P6_X_FULL_CI=HOLD_NATIVE_LANES`, `P7_FINAL=HOLD`**. The strict P5-X exact-head binary receipt is pinned to `52067302...`, so it does not independently constitute `3b447b...` exact-HEAD executable acceptance despite unchanged Physics source blobs. `SCIENCE_HOLD`, Native P3/P4 `NOT_RUN`; main and #665 unmerged.

**Follow-up ownership:** P6-X single Writer may only promote latest exact-head Native ownership after the independent Public D 100-row/new Physics contract (and FLOW/ARCH separate authority) is met, or record an explicitly authorized lane disposition that does not hide real CI failure. P7 incorporates both the passing C3 evidence and negative results; it does not equate failure with a completed release gate.
