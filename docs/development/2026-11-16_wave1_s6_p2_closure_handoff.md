# Wave1-S6-P2: independent completion gate and selective integration handoff

**Date:** 2026-11-16 UTC
**Owner:** ARCH, S6-417 / S6-941 only
**Authority:** Issue #541 (integration), #535 (workflow retirement), #402 (science)
**Verdict:** S6-417 P2=SOURCE_BOUND_PASS; S6-941 P2=SOURCE_BOUND_PASS; P3 replay=KEEP_HOLD; original workflow=KEEP_HOLD; science=SCIENCE_HOLD.

## 1. Independent P2 evidence: no costly P3 required

- Exact integrated source: 5d15c4054a00aa9fa8a778a87bb21690a3a5469b at Draft #578.
- [Repository CI #43883076025](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43883076025): job 133353818041, Issue541 ARCH S6 417+941 hybrid native P1/P2 exact-source (no P3), terminal SUCCESS.
- Observed Native log: ARCH_S6_CASE=417 P2=PASS P3=NOT_RUN SCIENCE_HOLD STATUS=ARCH_S6_HYBRID_NATIVE_P2_PASS_NO_P3.
- Observed Native log: ARCH_S6_CASE=941 P2=PASS P3=NOT_RUN SCIENCE_HOLD STATUS=ARCH_S6_HYBRID_NATIVE_P2_PASS_NO_P3.
- [Artifact #14234186951](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43883076025/artifacts/14234186951), size 8,675 bytes, ZIP SHA-256 7d2b1593f9ef7e4cbce714d637a9894a6109f2738e721be751ecb9609828f634. Previous #578 integration readback recorded ZIP CRC and full SHA PASS. Contains per-case status.json/native_P2.log, native_p1_identity.json and build log.
- Pinned historical checkout 29d1acc6ef7969908b86719e4b95c73a1565136d and pinned OCI image sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008.
- Exact code blobs: .github/workflows/ci.yml at 84cd7d60508f9a93739e50fa93dfc4405ddc8dc1; ci/guards/issue541_arch_s6_native_p2_only.py at 533dfa16395c041c610130f90d0489300fdd548f.
- The 11-layer Native P2 route executes source-bound check-input with an actual P1 binary for each variant. It is NOT a 100 microsecond time integration and does not establish P3/P4/scientific success.
- The existing P2 runner passes chemistry_cutover=chem_cutover from prepare_chemistry to prepare_hybrid, preserving each previously retired Native/JSON owner without a second removal.

**Precision:** P2 success is PROVEN for exact source 5d15c405. This new closure Draft does NOT assert a fresh Native P2 run at its own later SHA. If the integration HEAD changes, re-evaluate changed P2-relevant source and obtain fresh exact-HEAD P2 if release policy demands it.

## 2. New S6 P3 failure is separate

Owner explicitly attested no external S6 original workflow callers and authorized a bounded actual two-case 400 W / 100 us P3 attempt. [Run #43892446918](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43892446918), exact isolated #612 head 6efeb8bbc519914099380e02ad60364b1c87032f, terminated FAILURE in both matrix jobs:

| Case | Job | Phase | Diagnostic Artifact | Native P3 |
| --- | --- | --- | --- | --- |
| 417 | 133386980384 | Hybrid owner preparation BEFORE P2/P3 | 14236309715 | NOT_RUN |
| 941 | 133386979669 | Hybrid owner preparation BEFORE P2/P3 | 14237158635 | NOT_RUN |

Both errors: ValueError: HYBRID_OWNER_COUNT_Variables_log_e: 0.

The P3 path in run_canonical_s6_p3_once.py invokes Chemistry cutover and then prepare_hybrid(staged / option.p2.CHEM, ordered, case) WITHOUT the chemistry_cutover receipt. The owner log_e has already been retired; the second owner removal fails before the Native P2 input check or P3 timesteps. The independent P2 runner correctly passes chemistry_cutover=chem_cutover.

Classification: P3-specific input preparation regression, NOT failure of the separately proven P2 pathway. Repair, test and seek any further expensive replay only under a separate S6 P3 authority; do not make P2 completion depend on it.

Historical two-case 400 W/100us Native P3 at source af4a9e896328386723e8bbb957f334e1d83fe75e has archived results but historical Actions run was red after a literal Path("$RUNNER_TEMP") post-solve assertion. Maintained replay is not proved. Original workflow blob 485439a723584ca5bbc8632a86c53574b0b1eb9a must remain KEEP_HOLD.

## 3. Read-only P2 closure P0

ci/guards/issue541_arch_s6_p2_independence_p0.py validates the pinned receipt, exact source blobs, both case statuses, the immutable historical and OCI lineage, the Chemistry/Hybrid owner handoff, absence of Native P3 calls from the P2 runner, and fail-closed retirement/science constraints. It provides 14 synthetic negative mutations. It never launches a Native solver or requests a GitHub Actions job.

To run after checking out the candidate, execute:

    python3 ci/guards/issue541_arch_s6_p2_independence_p0.py --check --self-test

This is a STATIC receipt/contract test, not a replacement for separate external GitHub job/Artifact evidence. Do not treat a static PASS as new Native P2 PASS for a different SHA.

## 4. Instructions to the other integration Chat

**Selectively integrate ONLY the P2 closure Draft** into the existing #578 integration branch after reviewing exact source and running P0. It adds exactly three ARCH/S6-owned paths:

1. ci/baselines/issue541_arch_s6_p2_independent_closure_20261116.json
2. ci/guards/issue541_arch_s6_p2_independence_p0.py
3. docs/development/2026-11-16_wave1_s6_p2_closure_handoff.md

**Do not merge the separate entire Draft #612:** It includes an owner-approved one-shot P3 push workflow and unsuccessful P3 evidence and is NOT a P2 prerequisite. Do not merge Draft #575 to main merely for P2; it is a manual P3 bootstrap concern. Do not change common .github/workflows/ci.yml, workflow_surface_guard.py, DD P3, Wave2, Native Physics code, main, or the original S6 one-shot. Global workflow-surface policy remains an explicit HOLD: do not waive it or delete old workflows to make CI green.

| Gate | Verdict | Meaning |
| --- | --- | --- |
| S6-417 P2 | SOURCE_BOUND_PASS | Native check-input at 5d15c405 |
| S6-941 P2 | SOURCE_BOUND_PASS | Independent native check-input at same SHA |
| P3 new approved replay | KEEP_HOLD | Both jobs failed before Native input check |
| P4 | DIAGNOSTIC_ONLY | Not scientific acceptance |
| S6 original workflow retirement | KEEP_HOLD | Maintained replay and retention unresolved |
| External callers | OWNER_ATTESTED_ABSENT | User declaration for S6, not exhaustive machine audit |
| Full repository CI | KEEP_HOLD | Global validate still blocked |
| Scientific acceptance | SCIENCE_HOLD | No scientific parity approval |

**Coordinator request:** Record Wave1-S6-P2 as COMPLETE_AT_PINNED_HEAD and Wave1-P3-B as REPLAY_HOLD. Continue other Wave1 lanes without waiting for a costly S6 P3 solve. A changed integration HEAD may require new exact-HEAD P2 native proof; never claim the historical job ran on a newer source.

## 5. Post-integration cleanup ownership

The temporary one-shot in #612 is P3-only and must be cleaned up separately after its terminal failure/Artifact readback, without affecting this P2 closure. Any future source fix to the P3 owner handoff must be exercised by P0/scratch-only negative coverage before another costly P3 approval. The original historical workflow remains retained until #535 criteria are separately met.
