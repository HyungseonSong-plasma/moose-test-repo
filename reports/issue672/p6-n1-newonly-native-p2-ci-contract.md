# P6-N1 — S6 New-only-only Native P2 CI contract

> **Status: DESIGN_ONLY / SOURCE_BOUND_EVIDENCE_CONFIRMED / ACTIVATION_HOLD.**  
> This document is an independent P6-N1 worker artifact under [#672](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/672), not a new CI workflow, P5-X final acceptance, permission to run numerical P3/P4, or scientific parity approval.
> Prepared against Draft [PR #665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) HEAD `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f` (source HEAD must be re-read at activation).

## 1. Goal, authority and exclusion

**Proposed new check:** `newonly-s6-native-p2`. Its sole acceptance target is **both** real S6-417 and S6-941 disposable, 11-layer **New-only** inputs, checked by **one exact-final-HEAD** PhysicsApp `physics-opt` executable and its immutable runtime libraries. Required test set: two clean Native `--check-input` cases, an exact 12 FVKernel + 12 FVBC *actual C++ Warehouse* census per case, the electron/energy/pressure/Poisson/Wall/Surface Current constructor-consumer handoff, and 16 actual Native fail-closed negative controls (N1–N8 × two cases), all under the same pinned source/binary identity.

This lane must **not** replace, retarget, skip, neutralize or silently mark green any historical Public B (10-layer), Public D, FLOW D, ARCH Hybrid, Ion-FVM or #578 receipts. Those have distinct approval, regression and failure contracts. A successful New-only lane cannot certify historical Hybrid or vice versa. CI `validate` is independently required; it is not a substitute for Native. #535/#541 workflow-surface governance and P6-C1/C2 audit are mandatory before the P6-C3 single writer integrates workflows/templates.

**Scientific non-goals:** no timestep solve, native science P3/P4, RF-power 100-us replay, 150/200-step fallback, profile comparison, numerical equivalence approval, private rate publication, change to protected original ZIP/mesh/chemistry, or `main` merge. `SCIENCE_HOLD=true` regardless of P2 result.

## 2. Existing evidence and why it is not a final same-head acceptance

| Role | Actual run/artifact | Source/binary qualification | Observed |
|---|---|---|---|
| Normal S6-417 | [#44300489811](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44300489811), Artifact **#14425706979**, ZIP SHA256 `668815e6bcd15353586e177512cce45c32d1bb1e17d5ff0755fc4f6393105456` | Target `74a2b0f...`; W1 ELF SHA `cab62a4a9caa4d99a82564f31f915f1a7dc14565607712841123a30276d329bc` was built at **older** `05d7ce4...`; `w1_exact_head_match=false` | exit 0, `Syntax OK`, P05 reached; log SHA `e154a21a53c935bfb39e58dfd7f6ae81b5cd313450295bc6a2825e5848757071` |
| Normal S6-941 | Same [#44300489811](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44300489811), Artifact **#14425516960**, ZIP SHA256 `19180959b6dbd43aa748ddc900365eb1edcda22583d14275d62fd762f7a81990` | Same older-HEAD W1 ELF and target `74a2b0f...`; not exact source/binary HEAD parity | exit 0, `Syntax OK`, P05 reached; log SHA `c06952f0c600df4ef02a1d6a7580937ae75ae856e69b0e30e78fe004a0a50516` |
| Native N1–N8 × 2 | [#44300759948](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44300759948), Artifact **#14426253052**, ZIP SHA256 `a12af11831c40dc4fbc4ac0565efbb67ca2b62ba3fa5dfaa51637bd34c7d7225` | Source `74a2b0f...` pinned in receipt, diagnostic ELF SHA `47d891a09fde95ea6d12dc8ac4f85655c4001ca00ad592ddfd104459d8f0af4e` | 2/2 clean controls exit 0; **16/16 actual Native mutations exit 1, matching expected first failure**; original public file SHA restored; protected tmpfs removed |
| Warehouse and constructor bindings | [#44297119716](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44297119716), Artifact **#14423883385**, ZIP SHA256 `bcaeb9b1aff9cf28e26a5bc12eded70f13488876d0bce54dbf7691d16c49732b` | Separate instrumented PR #681 source `e68dc832e018aaa7e089d5a005d141d20974aed1`, ELF SHA `5d2f53a36c811a9561e397074dc734db05770929e6f2f1cf7e8bad04405e7a88` | Actual 12 FV Kernels +12 FVBCs **each case**, name/type/variable inventory and D8 constructor `getFunctor` bindings PASS; does not prove latest #665 HEAD numerical residual |

Independent ZIP SHA/CRC readback for all four artifacts and W2/W3/D8 included log SHA cross-check completed on 2026-11-18. The N1–N8 archive contains sanitized receipt and expected-hash metadata, **not raw negative logs**; never claim raw log SHA rehashed there.

The 16 mutations are **not all a P05-class error**: N1–N4 first fail at P05 (8 instances), N5 first fails during early object registration (2), and N6–N8 first fail in Chemistry validation (6). Every instance must match its exact expected error signature *and* a nonzero exit. A nonzero exit alone, or a generic error such as missing mesh/rate, is **FAIL**, never a negative-test PASS.

The above is strong feasibility evidence, **but P5-X signed/full final integrated acceptance is not yet verified** and the positive, negative and instrumented Warehouse proofs used differing binaries. Hence `P6-N1=DESIGNED`, `P6-N2/N3=BLOCKED_ON_P5_X`; no new green CI status from this document.

## 3. Immutable input and build pin (fail closed)

**G0 — admission / provenance**
1. Require the explicit P5-X final acceptance receipt for both cases with `accepted=true`, approving one exact PR #665 commit/tree and documented C++/generator/guard blobs. Treat null/missing/unreviewed receipt, moving HEAD, changed tested sources or `P5-X=HOLD` as `BLOCKED_DEPENDENCY`, **not** a green skipped job. Do not infer acceptance from a passing artifact on an older head.
2. Trusted checkout at exact 40-hex `target_sha`; re-read `git rev-parse HEAD` and tree hash at admission, immediately before protected data access, and before publication. CI/template source itself must be pinned. Wrong SHA or an unexpected workspace diff is a hard failure.
3. Pin OCI image **by digest** (currently `ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008`, refresh if P5-X approves change), compiler/toolchain, flags, source commit/tree and allowed factory registry.
4. **One build, one executable byte identity.** Build `physics-opt` once only, hash executable SHA256 **and** `libphysics-opt.so.0`, `libphysics_test-opt.so.0` (and runtime dependency manifest). Supply a read-only, verified binary/runtime bundle to both cases and all negatives; no parallel or case-local rebuild, and no old-HEAD W1 binary reuse under a strict current-head policy.

**G1 — actual real S6 disposable stage**
1. Create separate marked disposable Scratch directories for 417 and 941. Refuse symlinks, source-tree modifications, missing markers, stale inputs and missing exact P1 source manifest. Stage **11/11** `.i` inputs in immutable order and verify **each file and each transformed/deleted object block** by source/after SHA; this is the real P2→P3-X→P4-X cutover, not an invented fixture.
2. Pin 417 `unified_s6_417_newonly.json` SHA `ed99493d992c71b30e7a4120646af388894032d262b9af5bf299522629fe24ef`, 941 `unified_s6_941_newonly.json` SHA `2a7d6b191eddf6a92a6bcf74fc818ade8f30836fdd857dc70516f3aa57fa5dde`; C0 after P4-X SHA `2c3bab8a8e28b360dcd54775d91ba13c97401364c709944bc21d6bf0b6d79490`. Refresh only via an explicitly approved new P5-X source pin; do not silently update expected hashes.
3. Preserve original S6 400 W parent plasma mesh SHA `ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc`, RF/Maxwell child, transitive includes and separate `qvt.msh`; verify each by SHA. **Do not substitute** `qvt.msh` or another Issue397 L1/other-science mesh for the parent mesh.
4. Pin historical electron 42-row lookup SHA `35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b`, reduced/clamp gas-state semantics, 417 EI-417 **versus** 941 EI-941 reaction and layer; never copy 417 rate/branch SHA into 941.
5. Require **five original protected EI rate inputs per case** from the approved secure source. Verify approved source/destination/hash custody within protected runner and only publish allowed booleans/counts/digests. Private bytes, rate table rows, source access credentials and reconstructed full source paths must not appear in logs or artifacts. Zero/partial/incorrect rates = hard failure, not a synthetic fallback.
6. P0 strict preflight: JSON-selected `fem_species=e`, `fvm_species=O2p Om Op`, positive initial densities, canonical charge `(+1,-1,+1)`, correct transport/5:3 energy selector and gas Functors, no retired alias/owner, exactly one `carrier_one`, no 26 old ion FV owners, no 10 old electron BC/Material owners, no six P4-X competing materials, `dont_create_kernels` absent, all includes resolved. A source/static P0 PASS cannot certify Native Warehouse PASS.

## 4. Execution DAG and authoritative pass criteria

Proposed DAG; P6-N2 implements it **only after P5-X accepted**, P6-N3 executes after P6-N2:

```text
G0: approved P5-X + exact-head pin + trusted trigger
  -> G1: immutable source/input/mesh/Rate custody + source P0
  -> G2: build-once PhysicsApp binary + both app SOs + OCI evidence
     ├─ G3a: S6-417 clean --check-input
     ├─ G3b: S6-941 clean --check-input
     └─ G4: N1–N8 × 417/941 real Native negative mutations
  -> G5: C++ Warehouse/D8 exact object + consumer witness from same source/binary
  -> G6: sanitizer, independent receipt/ZIP digest, atomic two-case verdict
```

**G3 clean Native acceptance, per case:** actual `physics-opt --check-input` (never `-i synthetic_fixture.i`), exit **0**, exact `Syntax OK` evidence, reached P05 verification; case-specific complete log SHA and required runtime flags. A passing job with exit nonzero recorded as an expected diagnostic is not clean PASS. Include stable names and exact compiled Factory types/variables, not merely an `expected_count` field.

**G5 actual Warehouse acceptance, per case:** query real C++ non-linear-system Warehouse or independently instrumented check from **same compiled source/binary**:
- For `O2p`, `Om`, `Op`: exactly one each of `<id>_time:FVLogMolarTimeDerivative`, `<id>_diffusion:FVLogMolarDiffusion`, `<id>_drift:FVLogMolarElectrostaticDrift`, `<id>_source:FVCoupledForce`, on exactly `log_<id>`. Thus **12/12 FV kernels** with zero leftover Native FV kernels.
- Exactly one general `<id>_wall:FVFunctorNeumannBC` and three `<id>_{cover,wafer,focus_ring}_dielectric:FVLogMolarDielectricFluxBC` per ion: **12/12 actual FV BC Warehouse objects** on exact state, mesh sidesets and sign/`-1/N_A` contract; no native duplicates. Repeated JSON boundary groups do **not** inflate the unique object count.
- Exactly **8 actual electron FEM BCs** in correct particle/energy split, one physical `n_e_physical` and one canonical `e_wall_number_flux` producer; energy uses `fluid` 5/3 closure and a unique `log_e_energy`. Distinguish generated Physics owners from surviving non-overlapping diagnostic aliases.
- Three charged-ion `IonWallFluxMaterial` constructor bindings (`O2p:+1`, `Om:-1`, `Op:+1`), no old `PhysicsIonWallFluxMaterial` factory/helper alias; three signed net surface-current providers and three lower-D `sigma` consumers; Poisson RHS and density aliases, neutral pressure and electron lookup consumers each resolve to unique live Functors.
- D8 live **constructor getFunctor binding** and real RF/Maxwell child input/include/Transfer provenance must be evidenced. Constructor proof does **not** claim residual, face, RF energy transfer or 100-us scientific numerical parity; keep those in separate bounded D8/science receipts.

**G4 real Native negative controls:** N1–N8 one mutation at a time **per case** in an isolated Scratch copied from the verified clean input. Require exactly one intended modified file and its before/after SHA, every other public file SHA unchanged, clean base run exit 0, mutated `--check-input` exit nonzero, expected primary error signature, no earlier missing mesh/rates/Factory failure, and exact SHA restoration before the next mutant. Expected observed first-failure class for each case: N1–N4 `P05`; N5 `EARLY_REGISTRATION`; N6–N8 `CHEMISTRY`. Mark any unexpected error, skip, omission, mutated source leakage or original restore mismatch as FAIL. **16/16 required**, not 15/16 or static model tests.

**G6 aggregation:** both clean cases + 16/16 real negatives + both actual 12+12 Warehouse inventories + electron/consumer presence + secure cleanup + all identity assertions. A successful overall GitHub Actions run is insufficient if any substantive gate failed. Define `PASS_NEWONLY_NATIVE_P2` **only** when every required field is true on the same approved `target_sha` and one binary SHA; otherwise `FAIL_CLOSED` (test error) or `BLOCKED_DEPENDENCY` (P5-X not approved). `SCIENCE_HOLD=true` is invariant.

## 5. CI trigger, secrets and ownership controls

- **Design-stage event:** no workflow created or enabled by P6-N1. For P6-N2, propose **explicit authorized `workflow_dispatch`** from a protected/trusted workflow branch, with `target_sha` and `p5x_receipt_sha256` inputs, plus a controlled `workflow_call` only from an already vetted trusted caller if governance permits. Do not add broad `push`/untrusted `pull_request_target`, `schedule`, or automatic science triggers. New-only lane activation requires P5-X approval and P6-C1/C2 surface audit, then P6-C3 single-writer workflow/template integration.
- Minimal `permissions: contents: read`; trusted pinned checkout **before** any protected credential is materialized. Do not execute arbitrary fork/PR code with EI secrets. Use a protected secrets environment **only if it has actually been configured and approved**; no assumption that a particular environment currently exists.
- All original EI data and keys remain in an ephemeral private `tmpfs`, with trap-based cleanup even on failure; read-only mounted inputs, private file names/contents excluded from `set -x`, stdout, exported env, caches and artifacts. Explicit `tmpfs_private_removed_on_exit=true` plus no-private-data artifact scanner required, including on negative/error paths.
- Serial `build-once` + content-addressed bundle, then per-case parallel, isolated Scratch; one immutable bundle SHA includes executable + both .so files, verified before *every* execution. Do not let two workers update shared manifests, source files, CI YAML, templates, original meshes or rate data.
- `concurrency` should prevent overlapping same SHA/CI lane operations without marking an interrupted or skipped run green. Fail on partial uploads, log redaction failures, expired/missing artifacts, source drift, or security boundary violations.
- Keep historical workflow paths, their preserved runs and failure statuses unchanged. Only P6-C3 has write authority on `.github/workflows/ci.yml` and generated template parity; only P6-X may declare complete P6 acceptance. Do not alter `dont_create_kernels`, P05 guards, job skip flags or existing historical events as a convenience.

## 6. Required machine-readable receipt (schema outline)

```json
{
  "schema": "issue672.newonly_native_p2_ci.v1",
  "lane": "newonly-s6-native-p2",
  "execution_mode": "CHECK_INPUT_ONLY",
  "gate": "PASS_NEWONLY_NATIVE_P2 | FAIL_CLOSED | BLOCKED_DEPENDENCY",
  "p5x_acceptance": {"receipt_commit": null, "accepted": false},
  "identity": {
    "source_commit": null, "source_tree": null, "workflow_blob": null,
    "OCI_digest": null, "physics_opt_sha256": null,
    "libphysics_opt_sha256": null, "libphysics_test_opt_sha256": null
  },
  "cases": {
    "417": {
      "11_layer_sha256": null, "json_sha256": null, "mesh_sha256": null,
      "electron_lookup_sha256": null, "protected_rate_custody_pass": false,
      "P0_pass": false, "check_input_exit": null, "syntax_ok": false,
      "P05_reached": false, "warehouse_FVKernels": null, "warehouse_FVBCs": null,
      "warehouse_electron_FEM_BCs": null, "constructor_bindings_pass": false,
      "native_log_sha256": null
    },
    "941": {"same_required_fields_as_417": true}
  },
  "negative_tests": {
    "per_case_required": 8, "total_required": 16,
    "native_matched_expected": 0, "original_source_restored": false
  },
  "security": {
    "private_content_uploaded": false, "tmpfs_cleanup_verified": false
  },
  "artifact": {"zip_sha256": null, "independent_readback_verified": false},
  "native_P3": "NOT_RUN", "native_P4": "NOT_RUN", "SCIENCE_HOLD": true
}
```

The `941` shorthand is **documentation-only**, not a valid receipt: the actual N2 implementation must emit **complete separate fields for both cases**. A validator must reject missing, null or inconsistent mandatory values; no default true/0. Attach source-to-object proof (`name,type,variable,boundary,count`) and all 16 per-mutant (`case,id,changed_file,before_sha,after_sha,exit,expected_class,actual_class,log_sha,restore_sha`) records rather than only aggregate counts.

**Artifacts, allowlist:** concise immutable `manifest.json`, per-case sanitized `native-check-input.log` and full case owner inventories, per-mutant **sanitized** error-class receipts (logs only if proven safe), `binary-provenance.json`, independent `artifact-sha256.json`, `acceptance.json`. Never upload raw plasma private rate tables, credentials or prepared private Scratch; collect CI logs and artifact URL/SHA for reviewer.

## 7. Verdict truth table and handoff

| Condition | Lane result | Downstream |
|---|---|---|
| P5-X not formally accepted, no exact-head binary or unapproved protected-run trigger | `BLOCKED_DEPENDENCY` | N1 design is valid; **do not run/enable N2/N3** |
| Both 417/941 normal Native P2 pass but different binary/source heads | `FAIL_IDENTITY` for strict final contract | Rebuild one exact-head bundle and re-execute both |
| One case fails, one negative has wrong error class, 12+12 mismatches or custody invalid | `FAIL_CLOSED` | Record first actual error; P5-X/P6-X not accepted |
| Both clean cases exit 0 + 16 expected Native fails + per-case exact Warehouse/consumer census + all SHA/security conditions | `PASS_NEWONLY_NATIVE_P2` | Only Native P2; `SCIENCE_HOLD` remains true |
| Old Public/Hybrid/FLOW/ARCH job fails or is KEEP_HOLD | Independent status, **never inherited** | Preserve original failure/authority and P6-E ledger |

**Responsibility split:**
- **P6-N1:** this read-only design and source evidence; committed only as an isolated report.
- **P5-X:** independent official acceptance of latest full real P5 binary, Native P2/P05/warehouse/D8 and source integrity.
- **P6-N2:** implement the vetted runner and unit/guard tests **after P5-X PASS**, without touching shared CI unless assigned P6-C3.
- **P6-N3:** run the approved exact HEAD New-only CI and independently rehash receipts/outputs **after N2 + P5-X**.
- **P6-C3/P6-X:** sole integration owner for CI/templates and P6 package verdict, after #535/#541 governance and lane-specific PASS or documented KEEP_HOLD.

**Current conclusion, 2026-11-18:** `P6-N1_DESIGN=PASS`; `P5-X_FINAL_ACCEPTANCE=HOLD/NOT_VERIFIED`; `P6-N2=NOT_IMPLEMENTED`, `P6-N3=NOT_RUN`, `SCIENCE_HOLD=true`. No CI execution was triggered, and no protected data or production files were altered.
