# Wave1-B / FIX-ARCH-S6 — bounded source-bound diagnostic receipt

**Status:** PARTIAL_HOLD / P3 NOT_RUN / SCIENCE_HOLD. This receipt is not scientific or Native P2 acceptance.  
**Authority:** #535 retirement contract; #541 ARCH package and integration.  
**Source:** Draft PR #578 head `9e71762a5f45ab755481720e8beba314f59cd021`.  
**Wave1-B branch:** `issue-wave1b-arch-s6-native-p2-20261116`, independent child of exact #578 head; neither `main` nor #578 was modified.

## Original failed-run evidence

- Repository CI: https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43853584740
- Job: `133252079410` — ARCH S6 417+941 hybrid Native P1/P2 (no P3)
- Artifact: `14220775650`, digest `sha256:148c6a48234d09469083099060b562514157a85ee67ed9e6761e7df6dda03d05`
- ZIP members include `issue541_arch_s6_p2_evidence/S6-417/status.json` and `.../S6-941/status.json`; no `native_P2.log` for either case, so no Native P2 invocation occurred.
- Both case receipts: `P0=PASS`, `P1=PASS_SOURCE_BOUND_BINARY`, `P2=HOLD`, blocker **`HYBRID_OWNER_COUNT_Variables_log_e: 0`**, `P3=NOT_RUN`, `SCIENCE_HOLD`.
- P1 OCI: `ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008`.
- P1 binary SHA256: `940319678b530f671d6e10ba27a1e713deadaf9df4939e2f4d2b9881880bf217`.
- Historical mesh SHA256: `ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc`.
- The two cases stage distinct reaction overlays (EI-417 versus EI-941) and the same 11-layer hybrid route; both fail on the common preliminary ownership transition.

## Deterministic root cause

The ARCH job invokes `chemistry.prepare_s6_run_input.prepare()`, which already validates and retires four charged Native initial-condition variables (`log_e`, `log_O2p`, `log_Om`, `log_Op`) into the staged JSON, and validates/rebinds eight Native sheath BCs. It then invokes `prepare_hybrid_json_s6.prepare()`, which incorrectly expects those four Native Variables and eight pre-rebound BC owner types to still exist and attempts their migration a second time. The first failing check is the missing `log_e` Native owner. This is an **order/ownership handshake defect during disposable input preparation**, not a failed `physics-opt --check-input` and not evidence of a physics/scientific failure.

## Bounded implementation

Exactly three paths changed (three atomic single-file commits, GitHub blob CAS plus readback):

| Path | Before blob | After blob |
| --- | --- | --- |
| `experiments/Issue402_plasma_dsl_g1/chemistry/prepare_hybrid_json_s6.py` | `d0b71431927cefd137160a58714297afdfecd30b` | `8a76517c7863be77d8390cd04b0b3be055f2c147` |
| `ci/guards/issue541_arch_s6_native_p2_only.py` | `39218f083e2c0ef49e0ac3e60f24938a41b53304` | `533dfa16395c041c610130f90d0489300fdd548f` |
| `tests/test_issue402_hybrid_json_s6_owner_preflight.py` | `ae48006f87f22e6eab98b9bc90db3f579d35dd2e` | `1da0bd66a1562dd7e072afdaf43ba58b799d16f9` |

The hybrid code now accepts an **optional** validated Chemistry handoff receipt. In the ARCH route it checks the prior four owner identities, exact staged base hash, transferred density values, eight distinct sheath BC identities, parameter signatures, and new-block hashes before retiring only the remaining native energy/material/kernel owners. The old standalone direct-hybrid call path stays unchanged. The ARCH runner supplies the already-produced `chem_cutover` receipt. No old `.i` files, P3 workflows, P3 approval gates, physical flux terms, boundaries, or scientific criteria were modified.

## Verification and red gates

- Local lightweight source-level positive verification: `ARCH_HANDOFF_P0_SYNTHETIC_POSITIVE_PASS`.
- Local six negative mutations: BC boundary, wall flux, variable, type; incorrect owner count; incorrect native handoff SHA — all rejected.
- Added full fixture-based pytest positives for 417 and 941, plus eight parameterized negative handoffs (invalid receipt/BC/JSON density/reaction cross-mix). **Not yet run on the updated GitHub head.**
- `python -m py_compile` on the modified hybrid preparer: PASS locally.
- Same-head real ARCH S6 P1/P2, required workflow guards/harness, artifact readback, and independent case outputs: **NOT_RUN on this new branch**; no `FIX_VERIFIED` claim.
- Historical original ARCH P3 workflow files and manual-only replay authorization remained unchanged in the three-path branch diff. `SCIENCE_HOLD`, `P3=NOT_RUN`, `P4=NOT_RUN`.

## Parallel integration and next real gate

- Wave1-A Draft #579 modifies `run_chemistry_s6_p2_only.py` plus its FLOW-specific test, not these three files. Both issues originate in duplicate Chemistry/sheath preparation; FLOW avoids a second hybrid migration, while ARCH explicitly verifies a Chemistry-to-hybrid receipt for its distinct integrated seven-species JSON route. Review any subsequent changes to `prepare_hybrid_json_s6.py` before applying this blob.
- #565 modifies separate public S6 option/Chemistry P2 paths, not this three-path delta. Its P2 success cannot replace ARCH source-bound P2.
- #571 changes ARCH runner and manual P3 scaffolding in its own branch. This branch starts from #578's integrated copy; #575 manual-only P3 bootstrap is untouched.
- #568/#574 FLOW code and CI donors are inherited in #578, without modifying their files here.
- Required after capability-authorized Draft PR creation: create a parent-target PR against `integration-issue541-3-7-6a-8a1-8a2-8b-20261116` and separate **CI-only, never-merge** main-target validation vehicle if needed for `pull_request: main`; run P0 negatives, workflow guard and harness without waiver, pinned OCI real Native P1, independent S6-417 and S6-941 `physics-opt --check-input`, source-bound artifact/log readback, unchanged ARCH DD P1/P2. Keep P3 entirely disabled and do not merge into main without review.
- PR creation remains a **local Samuel capability-routing adoption gate** on the currently pinned central revision `9b335e3fbb9c5e8e323e382daeec56fa25336822`; unmerged Draft #576 is the separate proposed `GITHUB_PR_CREATE` adoption. Do not bypass this routing boundary or silently mix central revisions.

**Current verdict: PARTIAL_HOLD.** The original preparer blocker is specifically repaired in source; this is not proven until the updated exact-head real ARCH Native P2 jobs for *both* cases complete successfully.
