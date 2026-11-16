# Issue #541 / Wave1-A+B — source composition, not acceptance

- Created: 2026-11-16; work: FIX-ARCH-S6 staged against the independently updated Wave1-A integration.
- Source integration Draft #578 branch: `integration-issue541-3-7-6a-8a1-8a2-8b-20261116`, exact parent `b26f15cc8c5c44233cf895b6ff52a2bbb1cffdea`, containing Wave1-A scoped two-file FLOW change. Original #578 branch not modified here.
- This candidate branch: `issue-541-wave1ab-staged-validation-20261116`; three sequential one-file GitHub blob-CAS replays from Wave1-B `issue-wave1b-arch-s6-native-p2-20261116`.
- Imported post-image blobs:
  1. `experiments/Issue402_plasma_dsl_g1/chemistry/prepare_hybrid_json_s6.py`: `8a76517c7863be77d8390cd04b0b3be055f2c147`
  2. `ci/guards/issue541_arch_s6_native_p2_only.py`: `533dfa16395c041c610130f90d0489300fdd548f`
  3. `tests/test_issue402_hybrid_json_s6_owner_preflight.py`: `1da0bd66a1562dd7e072afdaf43ba58b799d16f9`.
- Three GitHub commit receipts: `e2f5c1c064eebec10f97ae2fc5afebf2781ba9ef`, `00a78e3de96a56a8229dcb34b9ada9a4b7cb2315`, `15059a7342aea7921226ff2c769b12de26576f37`. Each was verified by post-write Git blob readback.
- Exact diff versus #578 at composition: three paths, three commits, zero unrelated changes.
- Root cause from original failed #578 Artifact 14220775650: both cases ended before Native `--check-input` with `HYBRID_OWNER_COUNT_Variables_log_e: 0`. Chemistry already retired the four Native charged initial variables and rebound eight sheath BCs before Hybrid attempted the same migration. Wave1-B verifies the Chemistry owner-handoff receipts and then processes only remaining owners.
- Local synthetic source P0: one positive and six negative mutations PASS; Python bytecode compile PASS. Repository full pytest not validated because checked-out source archive used locally did not include native `s6_c0_physics_base_no_d1.i`. The additional repository tests have not yet run in GitHub.
- Exact current candidate Native `physics-opt` P1 build, ARCH S6-417 and S6-941 independent P2, original ARCH DD Native regression, source SHA/artifact readback: **NOT_RUN** on this new candidate. **Do not claim FIX_VERIFIED.**
- #576, the separate consumer Samuel `GITHUB_PR_CREATE` adoption, remains an open Draft and its exact-head Repository CI 43849626886 failed (validate legacy Workflow Surface; independent native JSON IC constraint). Samuel `GITHUB_PR_MERGE` requires successful CI; #576 is not merged. The current pinned central registry has no `GITHUB_PR_CREATE` route, so PR creation via the new capability remains gated. GitHub connector visibility alone is not route authorization.
- Intended Draft PR base after capability adoption: #578 branch at verified current head; if parent moves again, recompute diff/mergeability and revalidate. To run main-only `pull_request` CI for a branch-based child, use a **separate CI-only never-merge** validation vehicle after authorized PR creation.
- No P3 workflow, historical .i, manual approval, global surface guard, scientific source, or `main` was edited. `P3=NOT_RUN`, `P4=NOT_RUN`, `SCIENCE_HOLD`. #535 retirement decisions unchanged; no automatic integration or deletion.

**Verdict: PARTIAL_HOLD.** Source composition ready for exact-head P0/P1/P2 when safe CI route is authorized.
