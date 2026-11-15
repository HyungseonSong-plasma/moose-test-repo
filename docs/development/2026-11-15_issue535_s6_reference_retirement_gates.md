# Issue #535 — operational S6-417/941 P3/P4 reference and legacy retirement gates

**Date:** 2026-11-15. **Repository:** `HyungseonSong-plasma/moose-test-repo`.
**Status:** Read-only verified reference; not a new numerical run; scientific acceptance still **SCIENCE_HOLD**.

## Frozen operational reference

The implementation integrated in main through PR #523–#531 has a genuine **hybrid** (Physics JSON/FEM electron + original Native ion FV, neutral NS, wall, Poisson, RF and reaction progress) 400 W, 0–100 us S6-417/941 source-bound run. The actual validated source was `af4a9e896328386723e8bbb957f334e1d83fe75e`, *not* the current `main` SHA. See [Actions #43587161603](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43587161603) and machine receipt `ci/baselines/issue402_s6_hybrid_20261114.json`.

| S6 | Artifact ID | GitHub artifact ZIP SHA-256 | P3 | P4 |
| --- | --- | --- | --- | --- |
| 417 | 14117371106 | `563800ba985c3966d24aa0196fbe8ce46c9e1f5f1a1936685c6b5ff76c77a195` | PASS, 461 frames | DIAGNOSTIC_ONLY |
| 941 | 14120049502 | `87150a4b7db1647aa6a46731335ea1efa28a2998558cedd83df08d707c210d7e` | PASS, 461 frames | DIAGNOSTIC_ONLY |

Downloaded and SHA-256-checked **both actual ZIPs** on 2026-11-15. The internal `status.json`, `manifest.json`, `plasma.e`, `plasma.csv`, `unified_s6_*.json`, P2/P3 logs and P4 metrics match the recorded SHA-256s. The existing `verify_chemistry_p3_evidence.py` read-only integrity verifier was run on reconstructed ZIP results, passing both cases. The new reference wrapper additionally checks exact source/binary/OCI identity, positive P0/P1/P2/P3 statuses, P4 diagnostic-only status, native owner counts (10 + 9 retired source blocks, eight retained Native sheath BCs), 461 monotonic finite CSV observations ending at 100 us, and diagnostic values. The old Actions jobs were **red only after the real solves**, owing to a quoted-heredoc `Path("$RUNNER_TEMP")` assertion, and emitted both artifacts.

The repository `Repository CI` `issue402_s6_reference_receipt` job checks the manifest/negative mutations on its exact checkout. **It does not fetch the 190-MB archived ZIPs and must not be cited as a new P3 run.** Reverify real downloaded ZIPs using:

```bash
python3 ci/guards/verify_issue402_s6_hybrid_baseline.py \
  --manifest-check --self-test \
  --artifact417 /secure/path/issue402-S6-417-20261114.zip \
  --artifact941 /secure/path/issue402-S6-941-20261114.zip
```

The original source/binary proof and comparison are an **operational regression baseline only**. The public reference timestamp is UNKNOWN and coordinates are ASSUMED; neither public comparison, P4 diagnostic completion, nor runner exit=0 establishes original-private-rate, BC, coefficient, residual/Jacobian, or scientific equivalence. Do not promote to scientific acceptance.

## Retention blocker and safe retirement

GitHub archive expiration is **2026-12-29 14:09:44 UTC (417)** and **15:48:51 UTC (941)**. This metadata and ZIP digest alone **does not preserve the actual bytes**. Store a controlled long-lived copy of each full artifact with the SHA-256 receipt, access controls and an independent readback before retiring its only replay route. Until then, `durable_backup=NOT_PROVEN` and **HOLD** on the `issue402-hybrid-json-s6-p3-p4-once.yml` workflow. Never auto-trigger the expensive 100-us P3.

## Removal decision boundary

- **REWIRE first:** source-only and P2-only historical workflow obligations for deleted `RateCoeffMaterial`/`HeavyReactionRateMaterial`, then initial composition/live inlet/SCCM, then JSON boundary and reaction-reduction P2. Use the exact HEAD ordinary Native build and preserve each unique positive/negative P2; deletion requires no current/dynamic consumer and exact-head source-owned tests.
- **KEEP until proven:** original 417/941 10-layer source archives, private-rate boundaries, scratch-only remapping, ion FV kernels, neutral NS, Native progress, Poisson/RF and eight sheath BCs. These were used in the operational baseline.
- **P3/P4 HOLD:** historical `dd-json-p3-smoke-once.yml` has a unique two-step transient and `hybrid-json-s6-p3-p4-once.yml` has unique full S6 replay; each requires its own retention/replay ownership proof. A P4 diagnostic is not scientific parity.
- **Guard:** never loosen `ci/guards/workflow_surface_guard.py` or redirect retired branch-bound `push` triggers onto `main`; each retirement processes at most two concrete files/one dependent pair and records Git blob SHA, incoming caller graph, previous run, replacement owner and post-delete CI.

Known adjacent Draft work: [#536](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/536) (legacy symbol audit), [#539](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/539) (reaction-material P0 retirement), [#538](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/538) (separate FV kernel refactor). Do not merge or cross-mutate these automatically. The Issue #1 historical 14-file set stays intact.

**Next bounded pair for Issue #535:** `issue402-json-rate-native-once.yml` and `issue402-rate-coef-ideal-gas-native-once.yml`. Compare their exact P0 + H01–H05 Native P2 coverage with regular `plasma_native_regression`, wire any missing positive/negative cases and use that exact P1 binary before removing one proven orphan.
