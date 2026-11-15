# Issue #541 / #535 — ARCH two-workflow independent disposition (2026-11-15)

**Authority:** Issue #541's latest *end-to-end package* allocation overrides the former functional ARCH role. ARCH owns the entire P0/P1/P2/P3/caller/evidence/retirement outcome for the following two workflows. This branch contains manually gated replay **candidates**, not proof of replay execution or deletion permission.

**Baseline:** `main@71e112eb05d4645c82aab8861b99d6952ac4ac3e`. The old workflow trigger branch `issue-402-dd-plasma-boundary-action@af4a9e896328386723e8bbb957f334e1d83fe75e` still exists. Both old workflow entries use `push` filtered by their own YAML path on that historic branch. Neither old file has a `workflow_call`, `workflow_dispatch`, or `schedule` trigger. Repository literal code search identifies an S6 README reference but cannot rule out external, dynamic or historical consumers; therefore **caller-zero is NOT_PROVEN**. The branch and its source are not deleted or retargeted.

## Workflow 1 — independent DD JSON two-timestep sheath P3

| Contract | Evidence / disposition |
| --- | --- |
| Original | `.github/workflows/issue402-dd-json-p3-smoke-once.yml`, blob `068ef7f78b84b45dbf8c678522ada049d4a42b7a` |
| Historical source and run | `2354f69ec7c0f8f0a90e0b931cc42fd28804dc07`, [Actions #43536220786](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43536220786); P0/P1 passed, real P3 sheath transient **failed** (`P3_NATIVE_SHEATH_SOLVE_UNRESOLVED`). Its root cause is NOT resolved by the later S6 ZIPs |
| Original artifact | `14090046268`, 1,550 bytes, SHA-256 `d7ccb403173ef7a831e3ec9ad31a6c74c49c54dda20dfa839fe11b3331c572a4`, expires **2026-12-14 00:48:01 UTC** |
| Independent backup | Owner-only Google Drive file `1kcw5K_gvmyeydTDuddIHs3VHZCMhQCaL`; re-downloaded the ZIP, verified exact size/SHA-256 and CRC |
| Evidence defect | ZIP holds only `tmp/issue402_dd_json_p3_native_build.log` and `tmp/issue402_dd_json_p3_transient.log`. Original workflow used hidden `.issue402_dd_json_p3_evidence`; upload-artifact default excluded hidden directory. This historical ZIP does **not** prove status.json, CSV, Exodus or successful P3 |
| Replacement | `.github/workflows/issue541-arch-dd-p3-replay.yml`: **workflow_dispatch only**, requires exact source SHA and explicit `ISSUE541_DD_TWO_STEP_P3_APPROVED`, then pinned OCI P1 and same real two-step P2/P3 runner. Evidence is written to visible `issue402_dd_json_p3_evidence` and always uploaded |
| Decision | **KEEP_HOLD**: missing successful maintained exact-head P3, caller-zero and approval/actual run evidence. P4 and S6 are not applicable to this small sheath smoke. `SCIENCE_HOLD` |

## Workflow 2 — historical hybrid S6-417 and S6-941 400W/100μs P3/P4

| Contract | Evidence / disposition |
| --- | --- |
| Original | `.github/workflows/issue402-hybrid-json-s6-p3-p4-once.yml`, blob `485439a723584ca5bbc8632a86c53574b0b1eb9a` |
| Pinned source / history | `af4a9e896328386723e8bbb957f334e1d83fe75e` from Actions [#43587161603](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43587161603); separate historical checkout `29d1acc6ef7969908b86719e4b95c73a1565136d` and pinned OCI `sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008` |
| Original ZIPs | 417: `14117371106`, `563800ba985c3966d24aa0196fbe8ce46c9e1f5f1a1936685c6b5ff76c77a195`, 98,686,127 B; 941: `14120049502`, `87150a4b7db1647aa6a46731335ea1efa28a2998558cedd83df08d707c210d7e`, 98,635,164 B. Both expire **2026-12-29** |
| Preservation | S6 originals independently copied to private Drive and downloaded/rehashed in ARCH [PR #543](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/543). #544 carries a canonical readback receipt. ZIP preservation **does not establish WORM retention** |
| Historical semantics | Both native P3 real solves contain 461 finite 0–100μs time rows. P4 is **DIAGNOSTIC_ONLY**, `SCIENCE_HOLD`; historical overall CI was red from a post-solve quoted `Path("$RUNNER_TEMP")` check bug |
| Replacement | `.github/workflows/issue541-arch-s6-p3-p4-replay.yml`: manual dispatch only, exact SHA plus **separate** `ISSUE541_S6_400W_100US_BOTH_CASES_APPROVED`; preserves both matrix cases, original public source/OCI/checker gates and always-upload artifacts; fixes quoted-heredoc path with `Path(os.environ["RUNNER_TEMP"])` |
| Decision | **KEEP_HOLD**: unique full-case replay has not been independently executed from the candidate HEAD, caller-zero absent, non-WORM retention and science parity unresolved. No automatic 400W P3 launch |

## Shared safety and acceptance checks

- `ci/baselines/issue541_arch_two_replay_20261115.json` pins the original workflow Git blobs, run/artifact IDs, full ZIP digest/bytes, backed-up evidence and explicit `KEEP_HOLD`. The two distinct P3 contracts are *not* interchangeable.
- `ci/guards/issue541_arch_replay_p0.py --self-test --check` independently checks the two manual workflow entrypoints, strict SHA and typed approval, original blobs, restricted scientific status and **10 fail-closed mutations**. CI job `issue541_arch_replay_p0` runs at the exact PR SHA.
- `ci/guards/workflow_surface_guard.py` allowlists **only** the two new manual entrypoints; the ten/eleven old branch-triggered YAML violations remain visible. Neither original one-shot is modified, rerouted to `main` or retired.
- A `workflow_dispatch` route is callable only when the workflow is present on the default branch. This Draft neither authorizes nor executes P3. Do **not** use static P0 PASS as P1/P2/P3 replay evidence.
- Retirement prerequisite for **each** candidate: explicit owner approval and cost gate; accepted exact-head P1, Native P2, real P3 and artifact/negative-proof; maintained replay with protected source/historical evidence; caller-zero proof beyond literal search; verified fallback/rollback. Otherwise retain the old workflow as `KEEP_HOLD`.
- Independent final integration remains centrally coordinated after each package has decided, but this ARCH package owns the entire technical closure for both of its workflows and will not delegate P3 to another chat.

**Rollback:** close the new Draft PR / revert only this branch's new manual entrypoint, CI gate, ledger and narrow guard allowlist entries; neither historical one-shot nor original private-rate/physics source was changed.
