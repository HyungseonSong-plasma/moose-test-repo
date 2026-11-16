# Wave1 internal selective intake — S6 P2, DD P3 gates, bounded S6 smoke, S6 replay P0

**Date:** 2026-11-16 UTC. **Destination:** Draft PR #578 integration branch ONLY. **Release verdict:** INTERNAL_STAGED / MAIN_KEEP_HOLD / SCIENCE_HOLD.

This record supersedes the implication that any pre-intake source SHA is the newly integrated head. Re-run all required CI on the final newly integrated GitHub HEAD, not the input sources listed here.

## Safe source intake (exactly scoped)

- **P2 independent closure:** three additive files from [Draft #617](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/617). Original pinned-source run [#43883076025](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43883076025) Native S6-417+941 P2 job #133353818041 SUCCESS; Artifact #14234186951 SHA256 `7d2b1593f9ef7e4cbce714d637a9894a6109f2738e721be751ecb9609828f634`. That frozen receipt remains explicitly tied to source `5d15c4054a00aa9fa8a778a87bb21690a3a5469b`.
- **Later independent P2 confirmation at parent head:** [Repository CI #43905832833](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43905832833), exact pre-intake source `632b95c8d80bdf578743c44091954b4bfeeb0e0a`, job #133434267281 SUCCESS for **both 417 and 941** (P3 NOT_RUN); Artifact #14244514106 ZIP SHA256 `c8355cdfd72c3c7cff4519c6f1dd860a49c10795c379e03a9ea837bd984df8c1`. This does not automatically prove new source after this intake.
- **DD P3 safety gates:** three DD-only files from [Draft #613](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/613) / [#610](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/610). Native DD P0/P1/P2 and negative controls passed at their original source [CI #43894158123](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43894158123), but actual DD two-step Native P3 has NOT passed; original DD Workflow must stay KEEP_HOLD.
- **S6 bounded 3-step mode:** single tested Runner file from [Draft #618](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/618), preserving the earlier `chemistry_cutover=cutover` fix. Explicit `bounded_three_steps` restricts Hybrid/Chemistry mode and timeout to <=3600s, forces three real Native steps at `3e-9` seconds; validates 4-row CSV and 4-frame Exodus; records `P3=BOUNDED_3_STEP_PASS`, `P4=NOT_RUN`, `SCIENCE_HOLD`. Full 100us default remains. Owner-authorized independent [S6 smoke run #43902067509](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43902067509) was SUCCESS on BOTH cases at source `c82d0d98e1e4033c24297ff752270c10200f3bc1`, jobs 133421014737 / 133421010491, Artifacts 14243685279 / 14243116086. This is proof at **that run's SHA only**, not at the newly integrated HEAD and not scientific/full 100us acceptance.
- **Maintained S6 Replay P0:** S6 manual-only workflow hardening and 20-negative source contract test from [Draft #612](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/612), without its temporary auto-triggering one-shot. Requires typed cost approval, exact source SHA, both 417/941, pinned OCI, mandatory source-bound artifact. The P0 contract is hooked in the manual-only S6 workflow; its execution on final integration source requires independent evidence.

## Explicit exclusions and authority boundaries

- DO NOT import the temporary owner-approved self-push S6 P3 Workflow from #612, CI-only PRs #614/#621, any Wave2 candidate, or delete/change either original ARCH P3 one-shot Workflow.
- DO NOT import [#620](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/620) original S6 YAML deletion while its own KEEP_HOLD acceptance gates remain unresolved. The preserved S6 original Git blob is `485439a723584ca5bbc8632a86c53574b0b1eb9a`; DD original `068ef7f78b84b45dbf8c678522ada049d4a42b7a`.
- DO NOT overwrite the later #578 A1 owner-attested/staged-retirement contract with outdated [#596](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/596) CORE/Group-A bridge assumptions. Existing #578 has a more recent A1 contract and negative checks.
- No shared `.github/workflows/ci.yml` or `ci/guards/workflow_surface_guard.py` changes, no main mutation, no default-branch workflow registration, no new P3 dispatch, no DD/S6 scientific acceptance.
- The full Repository `validate` previously FAILed for two original ARCH historical workflow branch policies. **Never call this PASS or waive either rule.** P3 Replay and original-workflow retirement remain separate KEEP_HOLD gates.
- Owner-attested lack of external callers is a scoped assertion, not complete independent enumeration. Preserve rollback/historical evidence and scientific holds.

## Coordinator acceptance after integration branch updates

1. Check the exact new source commit and bounded changed-file list; verify both original ARCH workflows are present with exact Git blobs, and `main` unchanged.
2. Observe new exact-source `Repository CI`: ARCH DD and S6 replay P0, 417+941 Native P2, CORE and FLOW Native P2. Report all job conclusions, including `validate` FAILURE if it persists.
3. Run additional read-only checks where a new P0 file is not automatically reached by CI, especially `python3 ci/guards/issue541_arch_s6_p2_independence_p0.py --check --self-test`; do not claim a local test was executed from source inspection alone.
4. Keep original DD and S6 P3 one-shot retirements `KEEP_HOLD`, P4 `DIAGNOSTIC_ONLY` or `NOT_RUN` as appropriate, `SCIENCE_HOLD`, and `main` merge `KEEP_HOLD` unless independently cleared.
