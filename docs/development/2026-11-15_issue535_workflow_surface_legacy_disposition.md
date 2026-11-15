# Issue #535 — workflow-surface legacy ownership and retirement ledger

**Date:** 2026-11-15. **Baseline:** `main@71e112eb05d4645c82aab8861b99d6952ac4ac3e`.
**Scope:** `HyungseonSong-plasma/moose-test-repo`; 11 pre-existing Issue402 one-shot YAMLs.
**Rule:** never bypass `ci/guards/workflow_surface_guard.py`, retarget historical workflows blindly to `main`, or infer scientific correctness from CI.
All retained one-shots are `push` branch-scoped; their non-`main` branch filters violate the current guard, and the reaction-reduction Native one-shot also has a multi-path filter.
A name-only source search cannot establish zero external API consumers.

| Historical workflow (under `.github/workflows/`) | Baseline Git blob | Observed work / consumers | Decision |
| --- | --- | --- | --- |
| `issue402-legacy-symbol-audit-once.yml` | `1931f0b9909507979826812f346d3353f12e333b` | Eight pytest modules and readonly symbol inventory. Replaced by exact-head `issue402_legacy_p0_inventory` with mutation self-test in Draft PR #536; prior job evidence 82 passed, 13 skipped. | **REMOVE ONLY IN #536**; still present on main and this PR's source base |
| `issue402-reaction-material-reduction-p0-once.yml` | `5e433b5c56f335808e6a5cbaa771b808eef1ad45` | Four pytest targets plus ten R2/R3/E8/Stage5 checkers. Self-file push on `issue-402-species-functor-naming` (branch lookup empty); exact filename search found only self-reference, no dispatch/reusable trigger. | **REMOVE IN #539** after exact-head replacement PASS; recoverable by Git blob/parent commit |
| `issue402-dd-json-boundary-p0-p2-once.yml` | `bbebff910db3e5659014368043a50b99273d2cdc` | Unique DD JSON boundary and negative Native P2 contracts; requires independent exact-head P2 handoff. | **HOLD: NATIVE_P2_OWNER_UNPROVED** |
| `issue402-dd-json-p3-smoke-once.yml` | `068ef7f78b84b45dbf8c678522ada049d4a42b7a` | Bounded two-step transient and Exodus/CSV evidence. | **HOLD: P3_REPLAY_AND_SCIENCE** |
| `issue402-hybrid-json-s6-p3-p4-once.yml` | `485439a723584ca5bbc8632a86c53574b0b1eb9a` | Public S6-417/941 400W hybrid P3/P4; specifically referenced in Chemistry README. | **HOLD: SCIENTIFIC_PROVENANCE** |
| `issue402-json-rate-native-once.yml` | `a24e8ab9c822edcf6bd7455957d0dd23d7aa1b51` | JSON/surface-rate P0, Native P1/P2 evidence. | **HOLD: NATIVE_P2_OWNER_UNPROVED** |
| `issue402-rate-coef-ideal-gas-native-once.yml` | `64164c097ec8f7831e67b80b317144cd97ba9ee8` | Ideal-gas and EI/H-rate source and Native P1/P2 evidence. | **HOLD: NATIVE_P2_OWNER_UNPROVED** |
| `issue402-reaction-reduction-native-once.yml` | `91313152e7e7df3bd0256a2180f489774cfa6171` | EI10/EI16 four Native P2 fixtures, full public S6 staging/replay; its multi-path trigger is not equivalent to self-path. #536 partially transfers checks, but replacement still has downstream legacy fixture failures. | **HOLD: NATIVE_P2_AND_REPLAY** |
| `issue402-sccm-fixed-gas-p0-p2-once.yml` | `9cfa70c6843fb3e4eeec572dc3df00fd4fe6b611` | Gas state/SCCM positive and negative Native P2 fixtures. | **HOLD: NATIVE_P2_OWNER_UNPROVED** |
| `issue402-species-initial-composition-native-once.yml` | `f11aa0de000fb05bcc587798400313558a6cb58a` | Species initial/inlet composition Native P0-P2 and evidence. | **HOLD: NATIVE_P2_OWNER_UNPROVED** |
| `issue402-species-live-ic-inlet-native-once.yml` | `c6068680c0c7083e38ec03d86c5433eb49db94bf` | Live species/inlet IC Native P0-P2 and negative mutations. | **HOLD: NATIVE_P2_OWNER_UNPROVED** |

## Exact source-bound proof for bounded deletion in #539

- Baseline historical P0-only workflow Git blob: `5e433b5c56f335808e6a5cbaa771b808eef1ad45`; original `push` trigger was limited to its own file on `issue-402-species-functor-naming`. No `workflow_dispatch` or `workflow_call`.
- Replacement: ordinary `.github/workflows/ci.yml` job `issue402_reaction_material_p0` at Draft PR #539 commit `b39267223ccc202c9513f90a1efa87e9a2bafca7`. Independent GitHub Actions [run 43699338184, job 132766790759](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43699338184/job/132766790759): exact-head **25 pytest passed**; all ten historical source checkers passed, including `S5R_EI16_PRODUCTION_RATE_OWNER_RECOVERY_PASS`; owner and mutation self-test PASS.
- The replacement explicitly preserves historical September `mean_en_solved`/`R_ion_O2` identities and checks their scratch-only canonicalization to `e_energy_eV`/`R_EI415`. A retired dielectric electron-energy BC was removed from the *test dependency graph*; no physics or archived source was changed.
- Following deletion: verify Git source absence, guard contract still PASS, run replacement P0 at exact **new** head; any failure is HOLD and rollback to previous commit. Deletion does **not** make the overall workflow guard green because ten one-shots remain on this branch (and independent Draft PR #536 is not merged).
- Neither the absence of a GitHub branch nor exact-name source search alone proves zero external consumers. This decision is bounded to a push-only, old-branch self-triggered P0-only workflow whose check obligations have a successful exact-head canonical owner. No historical data or scientific P3/P4 execution is deleted.

## Next gate

For the other nine HOLD workflows, establish per-file active/dynamic invocation, exact historical evidence, public/archived replay obligations, replacement Native or P3/P4 gates and durable evidence before retiring any. Keep Issue #1's 14 canonical historical assets and Issue402 `SCIENCE_HOLD` unchanged. Do not merge #536/#538/#539 automatically or claim a full green CI.
