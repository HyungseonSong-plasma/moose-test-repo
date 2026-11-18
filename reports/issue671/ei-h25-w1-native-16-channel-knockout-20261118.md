# EI/H25 required-channel knockout — actual W1 Native negative experiment (2026-11-18)

**Verdict: NATIVE_REQUIRED_CHANNEL_COMPLETENESS=FAIL (0/16 channel-specific rejection).**

## Provenance and scope

- Parent work: #671 / #633; P5-X and P7 remain independent acceptance gates.
- One-shot GitHub Actions push run: https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44346361965 (run #44346361965, job exact-head-w1-native-p05, workflow source commit `48aa79cd9647b0a659078c745fc96d3acabee0c9`).
- Original exact Physics/Source W1: `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f`.
- One shared actual W1 `physics-opt` ELF SHA-256: `1bdc85c65f5847ae58d51c76f89f8e67c67291dc9b5ee842bcbab98c4a71befa`; two linked app libraries pinned by the W1 manifest. Immutable OCI: `sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008`.
- Sanitized artifact: https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44346361965/artifacts/14445704195; downloaded original ZIP SHA-256 `6e8924ea9cdbd820c5e2477995b830171adcdb081bdded345eed2708fd3e5751`, CRC PASS. Embedded `p05_negative_receipt.json` SHA-256 `b42eaf2b9be9394ed0b1bbb76dd6ecb1455a0c510063afb0075dc2896f3ac873`.
- Source comparison: PR #665 HEAD `52067302d16074592503d0ef6b903cc344f55a08` is 4 commits ahead of W1 but only workflow `.github/workflows/ion-fvm-hybrid-staged-dt.yml` and `tests/test_issue633_newonly_run_species_schema.py` differ; no Chemistry.C, DDContinuityEq.C or New-only JSON difference. This is **not** an exact latest-HEAD W1 binary claim.
- No private rate file contents in artifact, no original S6 file writes, no P3/P4 or long science timesteps.

## Exact mutation and acceptance condition

For each case and each of eight required reaction IDs, copy the immutable 11-layer New-only Scratch, delete **both** `reactions[id]` and `equations[id]` for exactly one channel from the case Chemistry JSON, keep the other seven channels and all other inputs untouched, stage original protected EI rate files in case-local `/dev/shm`, and call the identical W1 `physics-opt --check-input`. Both clean controls first returned exit 0 / `Syntax OK`. The 16 mutants actually ran; each had only the intended JSON-file delta and preserved the staged public originals.

Strict success would require Native nonzero exit **and** the *first Native error* to name the removed channel and identify it as missing. A generic failure or source-existence error does not pass this claim. The workflow's own string matching suffered an over-escaped regex; the source-independent post-download verifier independently recalculated classification from actual exit codes, removed-channel names, and archived first-error excerpts. This regex issue **does not change** the observed 14 clean Native accepts.

| Removed reaction + equation | 417 Native | 941 Native |
|---|---|---|
| EI-02 | exit 0 / Syntax OK — INCORRECT ACCEPT | exit 0 / Syntax OK — INCORRECT ACCEPT |
| EI-17 | exit 0 / Syntax OK — INCORRECT ACCEPT | exit 0 / Syntax OK — INCORRECT ACCEPT |
| EI-415 | exit 0 / Syntax OK — INCORRECT ACCEPT | exit 0 / Syntax OK — INCORRECT ACCEPT |
| EI-401 | exit 1 — generic Om source error | exit 1 — generic Om source error |
| EI-407 | exit 0 / Syntax OK — INCORRECT ACCEPT | exit 0 / Syntax OK — INCORRECT ACCEPT |
| EI-2069 | exit 0 / Syntax OK — INCORRECT ACCEPT | exit 0 / Syntax OK — INCORRECT ACCEPT |
| EI-417 / EI-941 | exit 0 / Syntax OK — INCORRECT ACCEPT | exit 0 / Syntax OK — INCORRECT ACCEPT |
| H25 | exit 0 / Syntax OK — INCORRECT ACCEPT | exit 0 / Syntax OK — INCORRECT ACCEPT |

**Observed verdict:** `NATIVE_CASES=16/16 EXECUTED`; `NATIVE_ACCEPTS_MISSING_REQUIRED_CHANNEL=14/16`; `GENERIC_OM_SOURCE_FAILURE=2/16`; `CHANNEL_IDENTIFIED_MISSING_FAILURE=0/16`; `REQUIRED_CHANNEL_CONTRACT=FAIL`.

EI-401 first error in both cases: `Selected FV species 'Om' requires a nonzero volume reaction source in Chemistry JSON.` It does not identify EI-401 by name. All remaining reactants/source contributions were left intact in each mutant.

## Independently verified protections and interpretation

- Both positive controls: exit 0 / Syntax OK.
- Per-case `source_restoration=SHA_ALL_PUBLIC_FILES_UNCHANGED`.
- `tmpfs_cleanup_verified=true`, source protected EI table bytes not published; 4 artifact members are sanitized receipts and identity only.
- Source-only `prepare_s6_newonly.py` requires the exact eight-ID set and catches removal before staging; **this P0 contract was not an autonomous W1 Native channel-required check**.
- `ChemistryData::hasSpeciesSource(id)` checks if *any* volume reaction contributes to a species; a remaining source can mask a removed required channel. An explicit case-specific required-channel completeness contract is absent in the observed W1 runtime path.
- The current experiment intentionally did **not** remove `R_EI*` / `R_H25` producers, so producer-liveness negatives remain `NOT_RUN`. Their result cannot repair the proven whole-reaction deletion false acceptance; the missing-channel contract must be fixed first.

## Remaining gates

Add and test an explicit S6 417/941 eight-ID required-channel gate in the proper authority (without making the generic Chemistry JSON parser universally S6-only), then rerun both clean controls and the exact 16 Native deletions with **channel-named first-error signatures** under a new same-HEAD binary. Separately test missing `R_EI*` / `R_H25` kinetic producers if source-owner liveness is an acceptance claim. Preserve `P5_X_FINAL=HOLD`, `P7_FINAL=HOLD`, `SCIENCE_HOLD`, Native P3/P4 `NOT_RUN`; no merge or main changes.
