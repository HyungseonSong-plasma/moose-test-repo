# P7 final independent review — exact 9457191 (scoped package acceptance)

**Decision date:** 2026-11-18. **Reviewer scope:** P7 recovery-package P0/P1/P2 and bounded D8 3 ns only. This is NOT scientific release, long-duration P3/P4 authorization, main merge approval, or historical Hybrid acceptance.

## Formal disposition

- `P7_PACKAGE_FINAL=PASS_SCOPED_P0_P1_P2_AND_D8_3NS`.
- `P7_P1_CONNECTIVITY_CUTOVER=PASS_SCOPED_NEWONLY_417_941`.
- `P7_PUBLIC_D_ORIGINAL100_NEW_PHYSICS_P2=PASS_417_941` (no Public D long D8 or science approval).
- `P7_SCIENTIFIC_RELEASE=HOLD_SCIENCE_HOLD`; `SCIENCE_HOLD=ACTIVE`; 100us P3/P4 NOT_RUN; no 150/200-step automatic workflows.
- `P7_MAIN_MERGE=HOLD_EXPLICIT_REVIEW_AND_APPROVAL`; Draft #665 remains OPEN, not merged.
- `FLOW_HYBRID=KEEP_HOLD`; `ARCH_HYBRID=KEEP_HOLD`; `PUBLIC_D_HISTORICAL=KEEP_HOLD`; `ION_FVM_LEGACY=KEEP_HOLD_PRE_NATIVE`.

## Authoritative identity and execution evidence

- [Integration PR #665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) exact source HEAD `9457191f4c0693ae886586edd961965867ccd5c0`, tree `5444cfcba2d1cddd15322c4dc7f67cf23690b840`; open/draft/unmerged.
- [Repository CI #44366325757](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325757): exact pull_request HEAD, attempt 1, 20/20 jobs success; Workflow and generated Template identical Git blob `543de1708171f3bf9052f46c0baf927f14fd1c65`; P05 and fail-closed CI guards present.
- [One-build W1 #14458195502](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325757/artifacts/14458195502): original ZIP `d0b83a2cde6bea28546399236494392e3317cda7eeedeb5a71aa30f975ed7bef`; TAR `9622a3a37f2c144f622faec63e829fa7ef74dc2bebd5ed7fa7eec342bc3472eb`. Actual ELF `b327aea7f496809779dd233336d8c62d15ab021accdb13e552efe1a750c72e18`, libs `59f09eb9d88b42d5932bad848a7b3ff33faebfb843b3790247d868aea28abbee`, `31abf727e4a40d7e2d91a6ba45d26f9d7b682cde198cf4d43188609c53e33db8` verified directly from the three members.
- [New-only Native #14458752206](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325757/artifacts/14458752206): S6-417/941 `--check-input` 2/2 exit 0 and Syntax OK; each actual post-add registrations **12 FVKernel +12 FVBC +8 e FEM BC**, N1–N8 16/16 expected native refusals, original staging restoration and protected scratch cleanup PASS.
- [Public D 100-row Native #14459116868](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325757/artifacts/14459116868): separate S6-417/941 original table 100×3 SHA `994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387` preserved, Native P2 exit 0 both, same verified W1 binary, typed 12+12+8 each, N1–N8 16/16 expected refusals. Prepared 42-row reference is not equated with the original 100-row Public D input.
- [Current-HEAD W1 D8 run #44409942970](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44409942970), [Artifact #14475669657](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44409942970/artifacts/14475669657): exact frozen HEAD inside isolated workflow, **same W1 ELF without rebuild**, S6-417/941 real original post-P4-X 11-layer **New-only** RF-on Maxwell child / seven Transfers / 3 physical steps to 3ns, Wall/Current/Poisson numeric crosschecks. D8 original ZIP SHA `0348c6255d2a6e59a2c921fc8f4b7d47f5307259358bc74067216e543456e6f6`. 34 numeric diagnostics per case, assembled discrete-variable residuals (not direct kernel-entry trace). Prior independent [257/257 D8 audit](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/a159182d47ad308e2f982a31a011ca81d33d158a/reports/issue671/p5x-9457191-w1-d8-rf-3ns-acceptance-20261118.md) accepted within stated tolerances; no 100us parity inference.

## Independent final review and historical ownership

- New separate review downloaded **six original GitHub Artifact ZIPs**, checked SHA-256/CRC, W1 TAR and actual ELF+both library member hashes, identical W1 identity JSON across W1/New-only/Public D/D8, each two-case native P2/typed/negative receipt and D8 bounded numeric validity. **141/141 named checks PASS**; full local machine-audit JSON SHA `20e3f0a949123dfd1d04e0338357195d3156a1e194c93d7e4fbf0877889e1f27`. This is additional corroboration to the previous broad **385/385 Native audit** and **257/257 D8 audit**, not a replacement for their verified reports.
- Historical Public B original 10-layer P2 is a control-only PASS; current historical Public D 11-layer rejection is documented as `KEEP_HOLD` in [Public Artifact #14456672534](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325757/artifacts/14456672534). No compatibility D-only runner was added.
- ARCH historical Hybrid two-case P05 `log_O2p` / `ni_time` collision is an intended negative; [ARCH Artifact #14457016880](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325757/artifacts/14457016880) contains both hashed Native failures; no Hybrid P2 success claim.
- Independent [FLOW run #44366325812](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325812) completed failure, first observed `P2_S6_417_CHECK_INPUT_FAILED`; no unsupported 941 PASS inferred.
- PR #689 and #690 merged into #665 only; PR #687/#688 closed without merge after evidence custody. Open/unique PRs #678/#681/#682/#683/#684/#685 remain separate and **not automatically integrated or closed**. Their independent code/compatibility risks belong to merge or further feature review, not this restricted P7 P2 disposition.

## Important limitations / release gate

1. Tracing observes successful real `FEProblemBase` post-add registration and live P05 checkIntegrity; **does not capture a raw TheWarehouse in-memory traversal**.
2. D8 measured finite discrete variable assembled residual L2 and wall/current/Poisson diagnostics, **not direct `computeQpResidual()` entry tracing**. D8 applied to New-only 417/941, not a new Public D 3ns transient proof.
3. No 100us P3/P4 scientific validity, long transient numerical equivalence, production-science acceptance, or historical Hybrid repair has been established.
4. Latest `main=ebcfd9e662bc40f0473d8da05da95d11b61789f8`; #665 PR recorded base `fb77673d7bbbbeb389549929a8f57724c703ff7e`. The PR is **four commits behind main** and diverged, so merge requires a separate current-base conflict/consumer audit, exact new HEAD evidence as required, and explicit authorization. **Do not rebase/merge as part of this P7 review.**

## DoD mapping / transition

- Exact source/tree + W1/CI/Artifact P0/P1/P2: **PASS**.
- S6-417/941 unique Owner, 26 historical ion writers retired in disposable New-only/approved Public D, typed 12+12+8, Native N1–N8 16 per mode: **PASS**.
- Neutral/RF/Poisson/unmodified 11-layer inputs, private EI cleanup, bounded 3ns D8 same ELF: **PASS within tested scope**.
- Historical Public/FLOW/ARCH isolated failures and no P05 waiver: **PASS boundary / KEEP_HOLD modes**.
- Source/current repo issue status consistency: **PASS after P7 issue receipt readback**, while prior snapshots remain retained as history.
- P7 **package closeout: PASS_SCOPED**. **Science release / merge: HOLD**. Do not close or merge #665 or disable SCIENCE_HOLD.

This decision supersedes earlier P7 `HOLD_PENDING_SEPARATE_FULL_REVIEW` **for the scoped P7 package only**, not for scientific/release approval. It does not supersede or reinterpret raw experiments.
