# Issue #541 / ARCH (lane C) — S6-417/941 evidence retention readback

**Date:** 2026-11-15 UTC. **Owner:** ARCH only. **Decision:** `BACKUP_BYTES_VERIFIED / UNIQUE_REPLAY_HOLD / SCIENCE_HOLD`.

## Scope and authority

This is a bounded, read-only review of the **already-completed** 400 W / 100 μs hybrid JSON+Native S6-417 and S6-941 operational baseline. It makes **no** new Physics runtime/science acceptance claim and makes **no** change to the solver, original archived inputs, workflow YAML, CI routing, or the shared Draft PR #540. Coordinating issue: #541; retirement execution: #535; science authority: #402.

- Original source: `af4a9e896328386723e8bbb957f334e1d83fe75e`.
- Original Actions run: [#43587161603](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43587161603), two matrix cases, source-bound P0/P1/P2/P3 evidence.
- Integration/main inspected: `main@71e112eb05d4645c82aab8861b99d6952ac4ac3e`.
- Existing mixed-scope [Draft PR #540](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/540) is a **separate writer** and owns the canonical receipt `ci/baselines/issue402_s6_hybrid_20261114.json`, verifier, and its existing ARCH note. Do not amend #540 from this branch.
- GitHub compare of original source to inspected main changed only two added one-shot workflow YAMLs; there were no source/input deltas in that comparison.

## Actual artifact bytes: source download → independent copy → readback

Downloaded **both original GitHub Action artifact ZIPs**, checked their entire SHA-256 locally, verified ZIP CRC and critical nested member SHA-256 (status, manifest, P2/P3 logs, Exodus, CSV, integrated Chemistry JSON, P4 metrics), and checked source/P1 binary/OCI provenance and semantic markers. Then uploaded the **unchanged original ZIP bytes** to a new **owner-only, non-shared** Google Drive folder and downloaded both stored files independently to rehash their full bytes. Google Drive metadata confirmed each file's parent, size, `shared=false`, and owner-only permission. The independent Drive copies had the same SHA-256 and byte counts as the original GitHub ZIPs.

Private archive folder: [Issue402 S6 ARCH reference (2026-11-14)](https://drive.google.com/drive/folders/1KbxP1TjW1u-9cRttyLelo3M2hXjrAAKb). The links are **not public shares**; authorized storage owner access is required.

| Case | GitHub artifact | Bytes | ZIP SHA-256 (GitHub source = Drive readback) | Drive copy | GitHub expiry (UTC) |
| --- | --- | ---: | --- | --- | --- |
| S6-417 | `14117371106` | 98,686,127 | `563800ba985c3966d24aa0196fbe8ce46c9e1f5f1a1936685c6b5ff76c77a195` | [private ZIP](https://drive.google.com/file/d/1jDJIgLRyuk-Gpy2AhBYJmN3t2OjWdnZX/view) | 2026-12-29 14:09:44 |
| S6-941 | `14120049502` | 98,635,164 | `87150a4b7db1647aa6a46731335ea1efa28a2998558cedd83df08d707c210d7e` | [private ZIP](https://drive.google.com/file/d/1E7xzCeMqIUhBFHov1WsvDKBPkEB1PURf/view) | 2026-12-29 15:48:51 |

**Retention classification:** `INDEPENDENT_BACKUP_READBACK_VERIFIED`. The copies are independently present outside expiring GitHub Actions artifacts, privately access-controlled, and full-byte hash-checked. Google Drive has not been configured as a WORM/retention-locked repository: prevent accidental deletion and verify access/retention before treating this as permanent institutional archival storage. This does **not** authorize Workflow retirement by itself.

## What the evidence proves (and does not prove)

- Original P0/P1/P2/P3 status/provenance fields checked against exact source `af4a9e896328386723e8bbb957f334e1d83fe75e`, same OCI image `ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008`.
- Native P1 binary SHA-256: S6-417 `21a4fac4ee2d0e83d628399f8d2c5054a85691968d67bbcf8057835a29a3d853`; S6-941 `8cddb80bd0c0e0da4d137bb8785e47321af9e6f0cd708e8ac88f8b18a843dc07`.
- Each ZIP contains 15 members, including `plasma.e`, `plasma.csv`, integrated `unified_s6_*.json`, P2/P3 logs and P4 diagnostics. Nested SHA-256s match the #540 SHA-pinned receipt. Both CSVs have 461 finite, monotonically increasing rows from t=0 to t=100 μs; Native P3 logs contain `Finished Executing`.
- Chemistry cutover/Native ownership markers: nine retired chemistry owners, ten retired generated electron owners, eight Native sheath BCs retained, seven species and eight reactions. A negative mutation that changes `science` to `SCIENCE_ACCEPTED` is rejected by the independent read-only check.
- P4 comparison values are diagnostics only. S6-417: peak ratio `1.0224145157537288`, horizontal relative L2 `0.06848464101507847`, vertical relative L2 `0.03930191280350551`. S6-941: `1.0199766679131463`, `0.06904315414600136`, `0.039490758948861567`.
- Original jobs were marked failed after solver completion because a quoted Python heredoc used literal `Path("$RUNNER_TEMP")` in a post-solve assertion. Distinguish archived P3 evidence from the red Actions job conclusion; do not classify the whole run green.
- Public comparison reference timestamp remains `UNKNOWN` and coordinates `ASSUMED_R_0_TO_25_Z_0_TO_44_CM`. P4 is `DIAGNOSTIC_ONLY`; private-rate, boundary, coefficient, residual/Jacobian and scientific parity remain unaccepted. `SCIENCE_HOLD`.

The previous independent original-ZIP checker lives in PR #540 as `ci/guards/verify_issue402_s6_hybrid_baseline.py`. Once an ordered integration is accepted, run that verifier against the **Drive readback** ZIPs and its negative `--self-test` on the exact checkout. This is a historical byte/provenance check, not a new full S6 solve.

## Workflow disposition / FLOW handoff

| Owner / path | ARCH finding | Reason / required handoff |
| --- | --- | --- |
| FLOW: `.github/workflows/issue402-hybrid-json-s6-p3-p4-once.yml` (main blob `485439a723584ca5bbc8632a86c53574b0b1eb9a`) | **KEEP / RETIREMENT_HOLD** | The independent ZIP-copy gate is now evidenced, but the exact 400 W / 100 μs **two-case P3/P4 replay contract** has no independently proven maintained replacement route. FLOW must prove supported replay capability and live/dynamic callers, exact-source preservation and ownership before proposing any retirement. Do not convert the old branch-specific push trigger to `main` or execute expensive P3 just to green CI. |
| FLOW: `.github/workflows/issue402-dd-json-p3-smoke-once.yml` (main blob `068ef7f78b84b45dbf8c678522ada049d4a42b7a`) | **SEPARATE HOLD** | This is a different, explicit two-step JSON sheath transient; S6 417/941 archived outputs are **not** a replacement or an acceptance receipt for that P3 contract. |
| CORE/PR #540: `ci/baselines/issue402_s6_hybrid_20261114.json` and `ci/guards/verify_issue402_s6_hybrid_baseline.py` | **HANDOFF, no ARCH edit** | #540 currently encodes `retention.durable_backup=NOT_PROVEN` as an explicit self-check. Its sole writer should reconcile this separately verified Drive readback receipt and update semantics **after** ordered integration; never rewrite #540 concurrently or silently change a negative control. |
| Historical original experiments, PhysicsApp C++, live Native P2 fixtures | **NO CHANGE / IMMUTABLE WHERE FROZEN** | Outside ARCH scope. CORE controls test-only fixture normalization; FLOW controls YAML/CI routing; #402 controls science acceptance. |

**Exit classification:** `ARCH_REFERENCE_BYTES=VERIFIED; ARCH_PRIVATE_DRIVE_READBACK=PASS; ARCH_UNIQUE_P3_P4_REPLAY=HOLD; SCIENCE=HOLD`. This clears **only** the independent backup byte-preservation question, **not** Workflow deletion, production cutover, or scientific parity. Retain #535 and #402 gates.
