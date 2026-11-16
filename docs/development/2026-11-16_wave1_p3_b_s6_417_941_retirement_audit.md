# Wave1-P3-B / Hybrid S6-417 and S6-941 — gated replay and retention audit

**Date:** 2026-11-16 UTC  
**Scope:** S6-only; no DD P3, shared CI/Guard, Wave2, Physics model, or main mutation.  
**Decision:** **KEEP_HOLD** for the historical issue402-hybrid-json-s6-p3-p4-once.yml.  
**Science:** SCIENCE_HOLD; P4 is DIAGNOSTIC_ONLY, never scientific acceptance.  
**Live P3 authorization:** NOT GRANTED in this work package; **no new Native P3 dispatched**.

## Source identity and historical original

- Parent integration: [Draft #578](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/578), initial exact HEAD 5d15c4054a00aa9fa8a778a87bb21690a3a5469b; main baseline 71e112eb05d4645c82aab8861b99d6952ac4ac3e.
- Historical YAML .github/workflows/issue402-hybrid-json-s6-p3-p4-once.yml Git blob **485439a723584ca5bbc8632a86c53574b0b1eb9a**, verified on integration HEAD and still-existing historical branch issue-402-dd-plasma-boundary-action. Its trigger is push to this same historical branch/path only, not workflow_dispatch / workflow_call / schedule.
- Original run [#43587161603](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43587161603), source af4a9e896328386723e8bbb957f334e1d83fe75e, immutable public checkout 29d1acc6ef7969908b86719e4b95c73a1565136d, pinned OCI digest sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008.
- Both matrix jobs are **FAILURE**, **after** Native solve: job 132424030324 (417), 132424030094 (941). Original job logs prove a post-solve AssertionError due to the quoted Python heredoc literal Path("$RUNNER_TEMP"). Do not relabel the historical Actions job as green.

## Separate case-by-case original evidence

| Field | S6-417 | S6-941 |
| --- | --- | --- |
| Power / duration | 400 W / 100 us | 400 W / 100 us |
| Original artifact ID | 14117371106 | 14120049502 |
| ZIP bytes | 98,686,127 | 98,635,164 |
| ZIP SHA-256 | 563800ba985c3966d24aa0196fbe8ce46c9e1f5f1a1936685c6b5ff76c77a195 | 87150a4b7db1647aa6a46731335ea1efa28a2998558cedd83df08d707c210d7e |
| Expiry (UTC) | 2026-12-29 14:09:44 | 2026-12-29 15:48:51 |
| Historical P1 binary SHA-256 | 21a4fac4ee2d0e83d628399f8d2c5054a85691968d67bbcf8057835a29a3d853 | 8cddb80bd0c0e0da4d137bb8785e47321af9e6f0cd708e8ac88f8b18a843dc07 |
| P3 observed evidence | 461 finite monotone CSV rows, t=0..100 us, native log Finished Executing | 461 finite monotone CSV rows, t=0..100 us, native log Finished Executing |
| P4 ratios (peak, H-L2, V-L2) | 1.0224145157537288, 0.06848464101507847, 0.03930191280350551 | 1.0199766679131463, 0.06904315414600136, 0.039490758948861567 |
| Science | SCIENCE_HOLD | SCIENCE_HOLD |
| Maintained exact-head replay | NOT_RUN | NOT_RUN |
| Disposition | KEEP_HOLD | KEEP_HOLD |

The historical ZIPs have live GitHub artifact digests matching the full SHA-256 values above. Prior independent [#543 retention readback](2026-11-15_issue541_arch_s6_retention_readback.md) records ZIP CRC, 15 members each, source/OCI/binary and nested manifest/log/CSV/Exodus hashes, and private Google Drive copies downloaded back with full-byte SHA-256 equality. **This work session rechecked GitHub metadata and original job logs; it did not redownload/re-hash the approximately 197 MB original ZIP bytes.** The Drive copies are not established WORM/retention-locked. Durability remains a separate gate.

## Maintained candidate, P0, and Native P1/P2

- Candidate .github/workflows/issue541-arch-s6-p3-p4-replay.yml on Draft #578 is workflow_dispatch ONLY. Typed cost approval ISSUE541_S6_400W_100US_BOTH_CASES_APPROVED and exact source_sha==GITHUB_SHA execute **before checkout/OCI/native execution**.
- Two distinct S6-417 and S6-941 jobs (fail-fast false, max-parallel 2, 360-minute job timeout each, 18,000-second P3 timeout per case). Real 400 W/100 us mode is selected; quick five-minute mode is disabled.
- Fixed post-solve path uses Path(os.environ["RUNNER_TEMP"]). The script requires --authorize-p3 and checks source/OCI/P1 binary identity, P2/P3 logs, status, integrated chemistry JSON. P4=DIAGNOSTIC_ONLY and science=SCIENCE_HOLD.
- Initial #578 exact-source [Repository CI #43883076025](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43883076025): combined ARCH replay P0 job 133353818435 **SUCCESS** with 14 negative controls; real S6 417+941 Native P1/P2 job 133353818041 **SUCCESS**, artifact 14234186951; P3/P4 NOT_RUN.
- This isolated branch introduces 20 S6-only fail-closed synthetic mutations in tests/test_issue541_s6_p3_replay_contract.py, wires this P0 test into the manual replay pre-P1 stage, and strengthens P3 artifact upload from if-no-files-found: warn to **error**. New-head tests require an independently observed run; their presence is not a PASS receipt.

## Caller and retirement audit

- Indexed accessible GitHub default-branch code search found the historical YAML as its own self-push trigger and a chemistry README reference. A README mention is documentation, not an execution caller. These observations **do not** prove zero dynamic/external callers.
- The historical branch retains the original P3 YAML. This package does not retarget its push event, remove an original, change main, weaken a global guard or delete artifacts.
- **External PAT, private runner/Controller, Actions API invocation, alternate refs, other accessible and inaccessible repos, and off-platform writers have NOT all been proven absent for this specific S6 original.** Prior owner statements scoped to A1 cannot be silently extended to S6.
- The manual replay workflow is **not on main** as of this audit. [Draft #575](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/575) proposes separately reviewed default-branch registration; it remains DRAFT/unmerged. A staged manual workflow is not a proven callable replacement.
- RETIRED_VERIFIED requires explicit run/cost approval, valid default-branch registration, actual source-bound both-case 400W/100us P3, independent per-case artifacts/readback and rollback, protected P4 diagnostic boundary, external/dynamic caller-zero and durable retention proof. Until then the correct complete investigation verdict is **KEEP_HOLD**, not forced CI normalization.

## Integration handoff — #578, #535, #541

1. Integrate only this S6-specific Draft diff after exact-head review. Retain the original YAML and report the global workflow-surface FAIL as an unwaived blocker.
2. Treat approved default-branch registration (#575) and separate explicit P3 cost/execution approval as independent prerequisites. Neither is granted by this PR.
3. When authorized, pin selected feature/ref HEAD and submit its same 40-char source_sha. Execute both 400 W/100 us cases, verify separate source/OCI/binary/provenance and Artifact ZIP hashes. Keep P4 DIAGNOSTIC_ONLY and SCIENCE_HOLD.
4. Resolve dynamic/off-platform caller-zero and retention/WORM separately; only afterward consider a future bounded original retirement change. DD P3 and Wave2 remain outside this scope.

**Final investigation verdict (2026-11-16): S6-417=KEEP_HOLD; S6-941=KEEP_HOLD; original workflow=KEEP_HOLD; P4=DIAGNOSTIC_ONLY; SCIENCE_HOLD.**
