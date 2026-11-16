# Wave1-INT — release candidate coordination (2026-11-16)

**Disposition:** RELEASE_HOLD / REVIEW_ONLY / SCIENCE_HOLD / P3_P4_NOT_RUN.
**Scope:** coordination-only Lane C. This is not proof of Wave1-only technical closure, not a green CI verdict, not permission to deploy PR #575, and not an approval to merge or execute P3.

## Exact-source anchors

- Repository: `HyungseonSong-plasma/moose-test-repo`, main `71e112eb05d4645c82aab8861b99d6952ac4ac3e`.
- Integration: [Draft #578](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/578) source `5d15c4054a00aa9fa8a778a87bb21690a3a5469b`. 142 commits ahead, 0 behind main; 88 changed paths.
- Predecessor: [Draft #577](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/577) `ac8f8133b9a8e59a6a3ae8316abfb701b2b4a3cf`.
- Registration candidate [Draft #575](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/575): `7435c68e3d728867522ba775968fec43e99413fe`, open Draft, **zero submitted reviews** at inspection.
- Samuel pin: `9b335e3fbb9c5e8e323e382daeec56fa25336822`, manifest and registry verified.
- [Repository CI #43883076025](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43883076025) on exact #578 HEAD: **16 SUCCESS, 1 FAILURE**. The failed `validate` job is #133353818240. No overall CI PASS.
- Read-before branch `cleanup-wave1-release-20261116` starts at source SHA above. Only this document is authorized to change in the first bounded cycle.

## Wave separation decision

**Strict Wave1-only source composition cannot presently be certified.** #578 already contains portions of Wave2 #6-B, #14 and #8-A-2 in Native code, CI routes, source transformers and retirement guards. Removing these paths solely by label could break Wave1 P1/P2 and guard semantics. Preserve the currently validated integration content and require dependency-closed verification before considering any subtraction. **Formal Wave2 integration remains NOT_STARTED.** Classifications are release-handling scope, not full per-hunk git provenance.

## Path-level wave classification (88 files)

Column `#577` means present in the main→#577 delta. `later` means modified by the #577→#578 span. Shared paths demand change-level inspection even if listed in one group.

| Changed path vs main | Git status | Release category | #577 | Later | Safety handling |
|---|---|---|:---:|:---:|---|
| `.github/workflows/ci.yml` | modified | SHARED-WAVE1/WAVE2 | Y | Y | Lane C ONLY for edits; no blind overwrite |
| `.github/workflows/issue402-dd-json-boundary-p0-p2-once.yml` | removed | WAVE1-C | - | Y | A1 staged HOLD / A2 verified disposition |
| `.github/workflows/issue402-flow-native-p2-regression.yml` | added | SHARED-WAVE1/WAVE2 | - | Y | Lane C ONLY for edits; no blind overwrite |
| `.github/workflows/issue402-json-rate-native-once.yml` | removed | BASE-577 | Y | - | upstream dependency preserved |
| `.github/workflows/issue402-legacy-symbol-audit-once.yml` | removed | WAVE1-C | - | Y | A1 staged HOLD / A2 verified disposition |
| `.github/workflows/issue402-rate-coef-ideal-gas-native-once.yml` | removed | WAVE2-8-A-2 | - | Y | A3/A4 caller & evidence retention; formal Wave2 pending |
| `.github/workflows/issue402-reaction-material-reduction-p0-once.yml` | removed | WAVE2-8-A-2 | - | Y | A3/A4 caller & evidence retention; formal Wave2 pending |
| `.github/workflows/issue402-reaction-reduction-native-once.yml` | removed | WAVE1-FLOW-RETIREMENT | - | Y | retirement safety & caller evidence |
| `.github/workflows/issue402-sccm-fixed-gas-p0-p2-once.yml` | removed | BASE-577 | Y | - | upstream dependency preserved |
| `.github/workflows/issue402-species-initial-composition-native-once.yml` | removed | WAVE1-D | - | Y | CORE original retirement & P1/P2 |
| `.github/workflows/issue402-species-live-ic-inlet-native-once.yml` | removed | WAVE1-D | - | Y | CORE original retirement & P1/P2 |
| `.github/workflows/issue541-arch-dd-p3-replay.yml` | added | WAVE1-B | - | Y | Lane B owned DD/S6/P3; do not edit |
| `.github/workflows/issue541-arch-s6-p3-p4-replay.yml` | added | WAVE1-B | - | Y | Lane B owned DD/S6/P3; do not edit |
| `ci/baselines/issue402_s6_hybrid_20261114.json` | added | BASE-577 | Y | - | upstream dependency preserved |
| `ci/baselines/issue541_arch_two_replay_20261115.json` | added | WAVE1-B | - | Y | Lane B owned DD/S6/P3; do not edit |
| `ci/baselines/issue541_completed_tasks_integration.json` | added | SHARED-WAVE1/WAVE2 | Y | - | Lane C ONLY for edits; no blind overwrite |
| `ci/baselines/issue541_core_four_retirement.json` | added | WAVE1-D | Y | Y | CORE original retirement & P1/P2 |
| `ci/baselines/issue541_group_a2_flow_retirement.json` | added | WAVE2-8-A-2 | - | Y | A3/A4 caller & evidence retention; formal Wave2 pending |
| `ci/baselines/issue541_group_a_retirement.json` | added | WAVE1-C | - | Y | A1 staged HOLD / A2 verified disposition |
| `ci/baselines/issue541_group_b_flow_reaction_retirement.json` | added | WAVE1-FLOW-RETIREMENT | - | Y | retirement safety & caller evidence |
| `ci/baselines/issue541_six_unit_integration.json` | added | SHARED-WAVE1/WAVE2 | - | Y | Lane C ONLY for edits; no blind overwrite |
| `ci/baselines/issue541_wave1e_evidence_contract.json` | added | WAVE1-E | - | Y | HEAD vs merged-commit evidence guard |
| `ci/guards/issue402_ideal_gas_p0_contract.py` | added | WAVE2-8-A-2 | Y | Y | A3/A4 caller & evidence retention; formal Wave2 pending |
| `ci/guards/issue402_reaction_material_p0_contract.py` | added | WAVE2-8-A-2 | - | Y | A3/A4 caller & evidence retention; formal Wave2 pending |
| `ci/guards/issue402_symbol_inventory.py` | added | BASE-577 | Y | - | upstream dependency preserved |
| `ci/guards/issue541_arch_dd_p3_result_gate.py` | added | WAVE1-B | - | Y | Lane B owned DD/S6/P3; do not edit |
| `ci/guards/issue541_arch_replay_p0.py` | added | WAVE1-B | - | Y | Lane B owned DD/S6/P3; do not edit |
| `ci/guards/issue541_arch_s6_native_p2_only.py` | added | WAVE1-B | - | Y | Lane B owned DD/S6/P3; do not edit |
| `ci/guards/issue541_artifact_evidence_guard.py` | added | SHARED-WAVE1/WAVE2 | Y | - | Lane C ONLY for edits; no blind overwrite |
| `ci/guards/issue541_core_four_contract.py` | added | WAVE1-D | Y | Y | CORE original retirement & P1/P2 |
| `ci/guards/issue541_evidence_identity_guard.py` | added | WAVE1-E | - | Y | HEAD vs merged-commit evidence guard |
| `ci/guards/issue541_group_a2_flow_retirement_p0.py` | added | WAVE2-8-A-2 | - | Y | A3/A4 caller & evidence retention; formal Wave2 pending |
| `ci/guards/issue541_group_a_retirement.py` | added | WAVE1-C | - | Y | A1 staged HOLD / A2 verified disposition |
| `ci/guards/issue541_group_b_flow_retirement_p0.py` | added | WAVE1-FLOW-RETIREMENT | - | Y | retirement safety & caller evidence |
| `ci/guards/verify_issue402_s6_hybrid_baseline.py` | added | BASE-577 | Y | - | upstream dependency preserved |
| `ci/guards/workflow_surface_guard.py` | modified | SHARED-WAVE1/WAVE2 | Y | - | Lane C ONLY for edits; no blind overwrite |
| `ci/workflow_templates/general-ci.yml` | modified | SHARED-WAVE1/WAVE2 | Y | Y | Lane C ONLY for edits; no blind overwrite |
| `docs/development/2026-11-15_issue535_s6_reference_retirement_gates.md` | added | BASE-577 | Y | - | upstream dependency preserved |
| `docs/development/2026-11-15_issue541_arch_s6_retention_readback.md` | added | BASE-577 | Y | - | upstream dependency preserved |
| `docs/development/2026-11-15_issue541_arch_two_p3_replay_disposition.md` | added | WAVE1-B | - | Y | Lane B owned DD/S6/P3; do not edit |
| `docs/development/2026-11-16_wave1ab_staged_validation_receipt.md` | added | WAVE1-B | - | Y | Lane B owned DD/S6/P3; do not edit |
| `experiments/Issue402_plasma_dsl_g1/chemistry/oxygen_s6_p2_transport.json` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/chemistry/prepare_hybrid_json_s6.py` | modified | SHARED-WAVE1/WAVE2 | - | Y | Lane C ONLY for edits; no blind overwrite |
| `experiments/Issue402_plasma_dsl_g1/chemistry/prepare_s6_run_input.py` | modified | SHARED-WAVE1/WAVE2 | Y | - | Lane C ONLY for edits; no blind overwrite |
| `experiments/Issue402_plasma_dsl_g1/chemistry_s6_417_catalogue_p2.i` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/chemistry_s6_941_catalogue_p2.i` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/chemistry_two_channels.i` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/compare_native_outputs.py` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/invalid_fem_fv_swap.i` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/invalid_incomplete_coefficients.i` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/invalid_legacy_kernel_names.i` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/invalid_missing_fvm_charges.i` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/invalid_missing_variable.i` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/invalid_species_density_nan_p2.i` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/invalid_wrong_charge_sign.i` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/noop_physics_root_overlay.i` | added | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/plasma_all_physics_json_p2.json` | added | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/plasma_two_channels.json` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py` | modified | WAVE2-6-B | Y | Y | preintegrated Native + D1 observer pair; no subtraction |
| `experiments/Issue402_plasma_dsl_g1/run_chemistry_s6_p2_only.py` | modified | WAVE1-A | - | Y | Lane A owned P0/P1/P2; do not edit |
| `experiments/Issue402_plasma_dsl_g1/run_native_binding_smoke.sh` | modified | BASE+INT | Y | Y | base #577 path also changed later; hunk-level audit |
| `experiments/Issue402_plasma_dsl_g1/valid_all_physics_json_p2.i` | added | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/valid_bindings.i` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `experiments/Issue402_plasma_dsl_g1/valid_generated_transport_json_p2.i` | added | BASE-577 | Y | - | upstream dependency preserved |
| `physics_app/ci/check_issue402_json_rate_native_p2.py` | added | BASE-577 | Y | - | upstream dependency preserved |
| `physics_app/ci/check_issue402_reaction_reduction_p2_only.py` | modified | WAVE1-FLOW-RETIREMENT | - | Y | FLOW Native EI10/EI16 P2 dependency; retain |
| `physics_app/ci/check_issue402_signed_fem_residual_native.py` | added | INTEGRATION-#3 | - | Y | Donor #566 signed FEM residual control; not full science acceptance |
| `physics_app/ci/check_stage5_s5r_ei16_recovery.py` | modified | WAVE2-8-A-2 | - | Y | Historical EI16 source identity vs current scratch mapping |
| `physics_app/ci/plasma_direct_existing_materials_smoke.i` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `physics_app/ci/run_issue402_dd_json_p3_smoke.py` | modified | WAVE1-B | - | Y | Lane B owned DD/S6/P3; do not edit |
| `physics_app/ci/run_issue541_core_four_native_p2.py` | added | WAVE1-D | Y | Y | CORE original retirement & P1/P2 |
| `physics_app/include/auxkernels/LowerDSurfaceCurrentProbeAux.h` | added | WAVE2-6-B | - | Y | preintegrated Native + D1 observer pair; no subtraction |
| `physics_app/include/auxkernels/WaferD1GeometryProbeAux.h` | added | WAVE2-6-B | - | Y | preintegrated Native + D1 observer pair; no subtraction |
| `physics_app/src/auxkernels/LowerDSurfaceCurrentProbeAux.C` | added | WAVE2-6-B | - | Y | preintegrated Native + D1 observer pair; no subtraction |
| `physics_app/src/auxkernels/WaferD1GeometryProbeAux.C` | added | WAVE2-6-B | - | Y | preintegrated Native + D1 observer pair; no subtraction |
| `tests/test_issue402_chemistry_mechanism_contract.py` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `tests/test_issue402_g1_external_species_binding.py` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `tests/test_issue402_hybrid_json_s6_owner_preflight.py` | modified | WAVE1-B | - | Y | Hybrid S6 owner/initial-state/sheath negative controls |
| `tests/test_issue402_json_rate_unification.py` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `tests/test_issue402_public_option_s6_p2.py` | modified | WAVE2-6-B | Y | Y | preintegrated Native + D1 observer pair; no subtraction |
| `tests/test_issue402_retired_plasma_closures.py` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `tests/test_issue402_s6_chemistry_run_templates.py` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `tests/test_issue402_species_initial_density_pairs.py` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `tests/test_issue402_species_transport_rule.py` | modified | BASE-577 | Y | - | upstream dependency preserved |
| `tests/test_issue541_flow_dbase_sheath_p2.py` | added | WAVE1-A | - | Y | Lane A owned P0/P1/P2; do not edit |
| `tests/test_issue541_flow_native_trigger.py` | added | SHARED-WAVE1/WAVE2 | - | Y | Lane C ONLY for edits; no blind overwrite |
| `tests/test_issue541_native_exodus_parity_oracle.py` | added | BASE-577 | Y | - | upstream dependency preserved |
| `tests/test_retired_legacy_physics_owners_contract.py` | modified | WAVE2-8-A-2 | - | Y | Retired BC vs active electron sheath owner contract |

## Release collision matrix

| Surface | Concrete conflict | Lane C resolution |
|---|---|---|
| `.github/workflows/ci.yml` and `ci/workflow_templates/general-ci.yml` | A/B/C/D/E jobs + Wave2 #14 and #8-A-2 overlap | Lane C alone reconciles shared contents; preserve trigger/job equivalence, re-run exact-head Repository CI |
| `ci/guards/workflow_surface_guard.py` | #575 blob `8f333782b1b2356d15504daf1bebcdc020e13c86` differs from #578 blob `477d6fdeca77edc01b3f40e4942475d2a575353d` | Do not wholesale-copy guard; preserve two narrowly allowed `workflow_dispatch` names, no original branch-filter waiver |
| DD/S6 manual replay workflows | #575 and #578 both include same new paths | Exact Git blob equality: DD `afb87cda2e4fec305af74637983daeb6fac1e14d`, S6 `8165bbc2c9776874a4b9dcf2590e271c0a876693`; register once after review, never auto-dispatch |
| ARCH original historical P3 one-shots | `issue402-dd-json-p3-smoke-once.yml` and `issue402-hybrid-json-s6-p3-p4-once.yml` still fail branch-policy | Both remain Lane B-owned KEEP_HOLD pending P3/rollback/caller proof; do not delete to silence guard |
| Wave2 #6-B six-file set | `public_option_s6_p2.py`, its test and four C++ Probe AuxKernels | Six exact blob SHA match #609; preserve Native P1/P2 + observer semantics; preintegrated does not imply formally approved Wave2 |
| Wave2 #14 FLOW Native trigger | `issue402-flow-native-p2-regression.yml`, `test_issue541_flow_native_trigger.py`, shared CI routing | Preserve actual PR event source coverage and fail-closed checks; avoid removing essential Wave1-A trigger |
| Wave2 #8-A-2 A3/A4 historical retirement | Two deleted original YAMLs, ledger/guard, FLOW P0/P2 | External/dynamic callers and artifact permanence not proven just by source-path absence; final retirement remains separate |
| Two S6 scratch preparations | `chemistry/prepare_hybrid_json_s6.py` and `chemistry/prepare_s6_run_input.py` overlap source-owner evolution | Retain sheath, initial density, D1 observer, 417/941 semantic checks and negative controls |
| Group A and CORE shared checks | A1 owner declaration vs dynamic-caller evidence, A2 disposition, CORE real P1/P2 | Preserve A1 integration HOLD, A2 scoped RETIRED_VERIFIED; verify 68 Group A negatives and source-bound P1/P2 |
| Wave1-E identity | Historical PR_HEAD/merged SHA relation | Do not mistake previous successful 29 negative controls for future #578 main merge; rerun audit against eventual actual merged commit |

## PR #575 registration / permission / approval checklist

- [x] Read #575 current HEAD and Draft/review state. No submitted reviews recorded.
- [x] DD & S6 manual workflow blobs on #575 and #578 match exactly; both use `workflow_dispatch` with explicit `source_sha`, typed approval and `contents: read`.
- [x] Main base inspected before staging; manual workflows do not exist on default branch. No dispatch initiated.
- [x] Scope of registration: 2 workflows + exact-event narrow allowlist, not legacy one-shot deletion or auto trigger.
- [ ] Independent ARCH owner/reviewer approval for reviewed default-branch registration, with 0 unresolved material review changes.
- [ ] Fresh main / #575 / #578 / Lane A/B exact-head read. Check shared guard difference and no duplicate CI job/event; guard self-test AND actual `--check` required without waiver.
- [ ] Check effective repository permission and branch gates with an authorized reader. Direct branch-protection endpoint returned 403; branch metadata said `protected:false`, rulesets query `[]`. Neither alone is sufficient authorization to skip review.
- [ ] Separate exact-source registration deployment approval. Only then use the governed exact-head PR merge/verification procedure; confirm both expected workflow blobs are present on **main**. Default-branch registration is not automatic from draft content.
- [ ] **Independent expensive runtime approval**: DD `ISSUE541_DD_TWO_STEP_P3_APPROVED`; S6 both 400 W/100 μs cases `ISSUE541_S6_400W_100US_BOTH_CASES_APPROVED`. Inputs must use fresh selected-source 40-character SHA and owner authorization; do not dispatch as part of registration.
- [ ] DD real 2-step P3 and S6 417+941 real P3 separately verify exact source/OCI/binary, solver evidence, artifact integrity, result oracle, caller-zero and rollback. P4 remains diagnostic, `SCIENCE_HOLD`.

## Wave1 gates and current CI classification

| Work | Verified #578 evidence | Still required |
|---|---|---|
| A / FLOW | Maintained FLOW Native run #43883075982 succeeded; P0/P1/P2 coverage | Lane A handoff at final exact source SHA; ensure no regression |
| B / ARCH | #43883076025 job #133353818041 S6 P1/P2 and job #133353818039 DD P1/P2 both succeeded | Two distinct authorized real P3 replays, provenance/caller & original workflow disposition |
| C / A1-A2 | A1 historical trigger sunset user-attested; A1 deletion staged; A2 RETIRED_VERIFIED; Group A job #133353817868 with 68 negatives succeeded | A1 integration acceptance and limited external-caller evidence, no false independent caller-zero claim |
| D / CORE | Historical P0 job #133353818981 + source-bound P1/P2 job #133353818289 succeeded | Three original workflow retirement final sign-off, rollback/CI exact-head |
| E / evidence identity | P0 job #133353817967, 29 negative controls succeeded | Historical PR_HEAD and merged-commit proof is NOT eventual release merge proof |
| **Global** | CI #43883076025 terminal **16 successful, 1 failed**; `validate` #133353818240 fails for exactly two ARCH historical branch-policy violations | No main merge while red; exact-release-head full CI/Artifacts, independent scientific gates |

**Fresh GitHub Artifact API metadata check (2026-11-16):** all five listed source-#578 artifacts exist, are not expired and advertise the expected SHA256 digests. ARCH S6 #14234186951 (8675 B, expires 2026-12-16); Group A #14232922962 (6097 B, 2026-12-16); CORE Native #14232683641 (2646 B, 2026-12-16); ARCH DD #14234060837 (2089 B, 2026-12-16); Wave1 E #14234070153 (1662 B, expires **2026-11-30**). This is a metadata availability check, not new ZIP-content readback. The coordinator documentation HEAD has **zero** CI runs as of inspection; exact-head validation for the candidate is NOT_RUN. Wave1 E artifact should be preserved before its earlier expiration.

Artifacts identified by existing #578 receipt (not replayed on a new branch SHA): ARCH S6 `14234186951`, Group A `14232922962`, CORE Native `14232683641`, ARCH DD `14234060837`, Wave1-E `14234070153`. Final HEAD requires independent job/attempt, artifact download, ZIP CRC, SHA-256 and inner source/binary/OCI readback. Never promote older successful SHA to current candidate.

## Lane A/B intake, final gate and Wave2 handoff

1. Require each Lane: source PR, current exact head SHA, changed-path and original-deletion manifest, original blobs/ref, reviewer decision, P0 mutation controls, P1 binary/OCI identity, true P2/P3 evidence classes, exact run/job/attempt ID, artifact ID/digest and rollback. No A/B ownership takeover.
2. Refresh #578/main and both lanes before each bounded CAS integration. Inspect path/hunk conflicts and preserve original behaviour. Lane C modifies only common CI/template/guard; each Lane retains DD/S6 source ownership.
3. Register manual P3 only after separate default-branch review. Preserve two original ARCH one-shots until accepted real replay and caller proof. No P3 launch from this document.
4. Exact final release HEAD: required guard `--self-test` + actual `--check`, workflow harness self-test/check, full P0 + source/OCI-bound Native P1/P2, independent P3 gates where required, full Repository CI SUCCESS with no red job, fresh artifact byte/provenance verification. Otherwise `RELEASE_HOLD`.
5. Never merge #578 into main on a red gate. After any actual authorized merge, read back actual merged-commit SHA and perform **independent post-merge Native verification**; PR HEAD result is not enough.
6. **Wave2 reference ancestry SHA:** `5d15c4054a00aa9fa8a778a87bb21690a3a5469b` (pre-release pinned intake only). **Final Wave2 handoff SHA: UNASSIGNED**, pending accepted Wave1 actual main merge plus post-merge Native verification. Wave2 formal integration has not begun.

## Mutation boundary

First bounded cycle only creates this new file on isolated `cleanup-wave1-release-20261116`. No edits to Wave1 A/B DD/S6-owned workflow/test files, no changes to `ci.yml`, workflow guard, production C++, `main`, #575, #578 or any existing PR, and no workflow execution/merge/retirement.
