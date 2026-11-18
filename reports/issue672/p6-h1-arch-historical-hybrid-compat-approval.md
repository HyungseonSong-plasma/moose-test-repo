# P6-H1 — ARCH historical Hybrid retention / compatible runner / approval disposition

> **Decision proposal, source review only (2026-11-18, UTC):** `HISTORICAL_HYBRID=RETAIN_AS_IMMUTABLE_ORACLE`; `CURRENT_HEAD_ARCH_HYBRID=KEEP_HOLD_P05`; `SEPARATE_PINNED_COMPAT_P2=CONDITIONALLY_RECOMMENDED_NOT_AUTHORIZED`; `NEWONLY_LANE=SEPARATE`; `P3_P4=NOT_RUN`; `SCIENCE_HOLD`.
>
> This report is **P6-H1** under #672. It does not grant operator authorization for P6-H3, workflow dispatch, CI edits, original deletion, Physics code changes, Native solves, or scientific acceptance.

## Exact provenance (do not substitute later head)

- Draft integration [#665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) reviewed at HEAD `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f`, not merged into `main`. Older ARCH FAIL logs belong to their own separately pinned commits.
- Archived original public input checkout: `29d1acc6ef7969908b86719e4b95c73a1565136d`; approved original input ZIPs and individual layer SHAs are unchanged historical references.
- Archived original S6 one-shot YAML Git blob: `485439a723584ca5bbc8632a86c53574b0b1eb9a`; on current `main` and Draft #665 this `.github/workflows/issue402-hybrid-json-s6-p3-p4-once.yml` path is absent, while `docs/development/archive/issue402-hybrid-json-s6-p3-p4-once.yml.txt` exists and has the exact same Git blob. Do not describe this as an active original workflow; archival retention is separate from workflow retention.
- Pinned historical ARCH P2-only baseline: source `5d15c4054a00aa9fa8a778a87bb21690a3a5469b`, immutable OCI digest `sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008`, [CI #43883076025](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43883076025), job `133353818041`, Artifact `14234186951`, ZIP SHA-256 `7d2b1593f9ef7e4cbce714d637a9894a6109f2738e721be751ecb9609828f634`; both 417/941 `P2=PASS`, `P3/P4=NOT_RUN`. This is **not** an exact-HEAD current Native result.
- Original 400 W/100 us historical P3 result: [run #43587161603](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43587161603), exact source `af4a9e896328386723e8bbb957f334e1d83fe75e`; archived two-case ZIP SHA/CRC and `Finished Executing`/461-row outputs independently retained, but historical Actions conclusion was **failure** due to quoted `Path("$RUNNER_TEMP")` post-solve assertion. P4 results are **DIAGNOSTIC_ONLY**, reference coordinates/timestamp unqualified and `SCIENCE_HOLD`.
- Subsequent historical replay [#43892446918](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43892446918) failed **before** Native P2/P3 (missing hybrid `Variables_log_e` owner) on a separate source commit; not a contradiction of the older pinned P2 PASS.

## Current ARCH conflict is physical ownership, not a missing file

- The exact HEAD [ARCH P2 runner](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f/ci/guards/issue541_arch_s6_native_p2_only.py) (Git blob `533dfa16395c041c610130f90d0489300fdd548f`) stages Chemistry→Hybrid **11 layers**, retains **26 existing Native ion FV owners**, and invokes the exact source-built `physics-opt --check-input` (never P3).
- The current Physics `DDContinuityEq.C` (blob `13b25226d463b8fd1e4acaee16358f8f17d710a0`) auto-generates 12 FV ion Kernels + 12 FVBC and runs P05 TheWarehouse `check_integrity` with same-variable/name/type/exactly-one checks.
- [Actual ARCH failure taxonomy in #672](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/672#issuecomment-6977558585): S6-417 **and** S6-941 fail on `log_O2p` old `ni_time [PhysicsFVLogMolarElectronTimeDerivative]`, diagnostic `P05 FV Native/Physics duplicate or unexpected owner`, staged `migrated_continuity.i:19.9`. This is a source-owner conflict; do not hide it by changing `dont_create_kernels`, weakening P05, blindly deleting historic native owners, or silently changing the legacy mode.
- Latest pinned [#44297212655](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44297212655) has `validate=PASS` (1566 passed/13 skipped), while the ARCH job still fails. Validation PASS does not clear the ARCH owner conflict.
- Separate [P5 New-only check-input #44300489811](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44300489811) is **New-only scope**; it is not a retroactive Hybrid P2 success, and P5-X full acceptance remains independent.
- Exact-head ordinary CI contains `issue541_arch_s6_hybrid_native_p2`, automatically run for in-repository PRs. It builds current head and repeats Hybrid P2, so it is not a stable historical-compatibility proof.
- **Drift in an old read-only guard:** `ci/guards/issue541_arch_s6_p2_independence_p0.py` (blob `20543b4e90655f1bf3c75ca28babc7a12031722c`) still reads the removed original workflow from `.github/workflows/...`; the immutable archival YAML is under `docs/development/archive/`. The frozen ledger also says `original_s6_workflow_retirement=KEEP_HOLD`, reflecting its old decision epoch. Correct the **current-state policy representation** under a separate owner-approved change; never rewrite the old evidence as if it were born at the new head.

## Disposition: two independent lanes, not a mode toggle

| Decision | Proposed result | Why |
| --- | --- | --- |
| Retain original S6-417/941 10-layer, derived 11-layer Hybrid, original ZIP/exodus/CSV and protected-rate SHA | **RETAIN** (immutable) | Historical numerical and semantic oracle; prevent loss of real 400W/100us evidence |
| Keep historical case graph as active current-head `ARCH Hybrid` P2 gate | **KEEP_HOLD** | P05 intentionally rejects 26 Native + 24 generated ion owners |
| Introduce a **separate historical compatible P2-only runner** | **CONDITIONAL / separate authorization** | Checkout pinned historically qualified source and exactly pinned input/OCI; do not run modern code as if it were old |
| Change canonical New-only production runner to accommodate Hybrid | **REJECT** | Would weaken New-only P05, mix 26/24 owners and corrupt acceptance boundary |
| Promote manual 100us P3/P4 replay to regression/release gate | **HOLD** | High cost and explicit operator/science permission needed |
| Automatically retire any additional workflow or rewrite historical receipts | **REJECT without #535/#541 approval** | Different owner and governance boundary |

## Proposed compatible runner contract for P6-H3 (no implementation in H1)

1. **Immutable historical checkout:** use reference source `5d15c4054a00aa9fa8a778a87bb21690a3a5469b` (or another separately approved, exact-sha qualified historical ref), original 417/941 archive at `29d1acc6ef7969908b86719e4b95c73a1565136d`; pin 11-layer manifest, JSON SHA, protected EI Rate custody and source tree/OCI/build command/binary SHA. No arbitrary current `main` HEAD or fallback to a moving branch.
2. **Isolated P2-only entry point** (new explicit manual workflow/job, *not* current PR-triggered ARCH regression): two separate disposable `0700` Scratch roots and case logs, exact provenance, read-only source/archives, `--check-input` **only**, no timesteps, no P3/P4, no private EI raw bytes in artifacts, no PR or source mutation.
3. **Fail closed:** source mismatch, missing/extra layer, wrong JSON/private lookup, OCI/binary mismatch, source-kind alias, unchecked original changes or output overwrite all return HOLD. Verify the historically qualified Factory/Native owner census without pretending the new 12+12 P05 result is part of that old run.
4. **Separate acceptance:** original P2 check-input exit 0, both case-specific receipts, identical source/binary/OCI identity, exact SHA and CRC readback, unchanged archived originals, no other caller side effects. A successful old runner earns `LEGACY_COMPAT_P2_AT_PINNED_HEAD=PASS` **only**; `NEW_ONLY_P2`, `CURRENT_HEAD_ARCH_HYBRID` and `SCIENCE_HOLD` remain independent.
5. **Modern compatibility is a different proposal:** to make Hybrid work at modern #665 HEAD, first obtain a distinct owner decision about whether the 26 Native ion owners are preserved in a non-generated historical lane *or* the 24 Physics owners become canonical in a new disposable migrated lane; prove full source/consumer semantics and P05 without bypass. That is a conversion, not “historical replay.”

## Approval matrix (not fulfilled by this report)

| Action | Evidence + human authorization required | If absent |
| --- | --- | --- |
| Historical retention/readback and read-only H1/H2 report | Existing #535/#541/#402 forensic authority, immutable hashes; no run | Allowed as analysis; no new science claim |
| P6-H3 **historical P2-only actual execution** | Operator explicitly approves exact source ref, both 417/941 cases, OCI/binary provenance, max P2-only scope, independent manual non-PR path, artifact retention/access | **HOLD — DO NOT DISPATCH** |
| Compat runner code/workflow/CI changes | #535/#541 workflow owner approval, bounded changed-file review, workflow-surface and generated-template parity, no new automatic long-running entry point; P6-X single CI writer | **HOLD** |
| Current-HEAD Hybrid migration/ion-owner cutover | Separate #633/#670/#671 P4-X/P5 approvals; zero duplicate owner, P05 preserved, actual P2 evidence; neutral/RF/Poisson/Wall/diagnostic caller parity | **HOLD** |
| 400W 100us manual P3/P4 replay | Separate operator authorization; `workflow_dispatch` exact `source_sha` **and** typed `ISSUE541_S6_400W_100US_BOTH_CASES_APPROVED`; two-case budget, protected inputs, evidence retention | **NOT AUTHORIZED / NOT_RUN** |
| Scientific equivalence / historical workflow retirement decision | #402 scientific authority + #535/#541 verified maintained replacement, dynamic caller assessment, archival retention governance/WORM and P4 independent acceptance | **SCIENCE_HOLD / no further retirement** |

## P6 handoff

- **P6-H1:** `REVIEW_COMPLETE__HISTORICAL_RETAIN__MODERN_ARCH_KEEP_HOLD__PINNED_COMPAT_PROPOSAL_NOT_AUTHORIZED`.
- **P6-H2:** read-only P05 `ni_time` exact-source conflict and 26-to-24 double-owner negative controls.
- **P6-H3:** do not dispatch until explicit pinned legacy P2-only approval and H2 integrity proof; otherwise issue a machine-readable `KEEP_HOLD` receipt with no runtime claim.
- **P6-N1/N2/C3/X:** New-only workflow separate from historical/ARCH and manual P3; P5-X exact binary/Warehouse gate and CI/workflow/template shared-writer conditions apply.
- Historical OCI/source, archive, mutable scratch and protected EI raw file contents remain unmodified; no CI or physics solve performed by H1.
