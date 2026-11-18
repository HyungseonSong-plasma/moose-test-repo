# P5-X — S6-417 / S6-941 actual Native evidence integrated; final acceptance HOLD

**Decision (2026-11-18):** `NATIVE_417_SYNTAX=PASS`; `NATIVE_941_SYNTAX=PASS`; `SHARED_ELF=PASS`; **`P5_X_FINAL_NATIVE_P2=HOLD`**; `SCIENCE_HOLD`. This receipt consolidates **existing** real GitHub CI artifacts; this integration job **did not launch** a new Native run, modify solver inputs or approve science.

## A. Immutable source and binary identity

- Review target: Draft PR [#665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) HEAD `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f`, tree `10ab018235f047bf1abc250d3b18005b9156752a`, main not merged.
- [W1 single-build artifact #14422701532](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44293156216/artifacts/14422701532): source **`05d7ce4eceb81769cb2f0146c51535fc35e74ac1`**, not current HEAD; exact ELF `cab62a4a9caa4d99a82564f31f915f1a7dc14565607712841123a30276d329bc` (67,368 bytes). `libphysics-opt.so.0` SHA `3274751989604b06e7e7e677435b16c874388a4f7b8735b059eafc605fbb7e51`; `libphysics_test-opt.so.0` SHA `86aa0d4ebe18d731e7e052f5ad62594b1a3b48074f848693b0958f728b61ba80`. W1 ZIP SHA `ce50a51f2ab565b5dc6aced272adcf12f1075f7593417c603ce05274c8291c18`, verified ZIP CRC and internal TAR/member bytes.
- Independent GitHub compare: `05d7ce4… → 74a2b0f…` = six commits, **only `tests/test_issue633_s6_scratch_ion_retirement.py` differs**. That supports C++ source equivalence but **does not satisfy the strict exact HEAD binary identity requirement**; both W2/W3 explicitly record `w1_exact_head_match=false`.

## B. Actual Native check-input (independent cases, same ELF)

| Case | Artifact | Exit / Syntax | Native log SHA256 | Verdict |
| --- | --- | --- | --- | --- |
| S6-417 | [#14425706979](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44300489811/artifacts/14425706979) | 0 / `Syntax OK` | `e154a21a53c935bfb39e58dfd7f6ae81b5cd313450295bc6a2825e5848757071` | **PASS_NATIVE_SYNTAX_OFF_HEAD** |
| S6-941 | [#14425516960](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44300489811/artifacts/14425516960) | 0 / `Syntax OK` | `c06952f0c600df4ef02a1d6a7580937ae75ae856e69b0e30e78fe004a0a50516` | **PASS_NATIVE_SYNTAX_OFF_HEAD** |

Both CI [run #44300489811](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44300489811) cases explicitly bind to ELF SHA `cab62a4a9caa4d99a82564f31f915f1a7dc14565607712841123a30276d329bc` and target source checkout HEAD `74a2b0f…`. Both have 11-layer file SHA **receipts** (their artifact ZIPs include receipt and log, **not all 11 raw staged .i bytes**), correct case-specific JSON (417 SHA `ed99493d992c71b30e7a4120646af388894032d262b9af5bf299522629fe24ef`; 941 SHA `2a7d6b191eddf6a92a6bcf74fc818ade8f30836fdd857dc70516f3aa57fa5dde`), final P4-X C0 SHA `2c3bab8a8e28b360dcd54775d91ba13c97401364c709944bc21d6bf0b6d79490`, original main mesh SHA `ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc`. Five protected EI Rate sources/case: secure Scratch cleanup true, no private data uploaded. Parent source original/41-step or science equivalence not inferred.

## C. Real observed P05 and D8 — **detached diagnostic heads, not final**

| Proof | Actual CI evidence | Observed | Acceptance boundary |
| --- | --- | --- | --- |
| Warehouse FV Kernel/FVBC | [Run #44280359966](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44280359966) artifact #14417221187 | **12 kernels + 12 FVBC**, each case; Factory/variable/name dump; one S6-417 O2p time duplicate rejected by P05 | Diagnostic HEAD `9e9b4f5…` ≠ current #665 |
| Constructor Functor binding | [Run #44297119716](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44297119716) artifact #14423883385 | 417 and 941 ion/electron density, wall, lower-D and current constructor binding; **12+12** | Diagnostic HEAD `e68dc83…`, no residual/face evaluation in this run |
| Wall/Surface Current FaceArg and residual | [Run #44303391987](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44303391987) artifact #14427412814 | Both actual case inputs + diagnostic overlay: 6 ion number/mass FaceArg values and 3 Lower-D residuals/case; RF off; exit 0 | Diagnostic HEAD `c78b824…`, **bounded** not full production RF |
| Maxwell child and 7 Transfers | [Run #44304244747](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44304244747) artifact #14428450104 | Both cases real child + production Transfer definitions in **reduced one-step parent**; exit 0, 12/12 checks/case | Diagnostic HEAD `7c37ca5…`; full coupled original S6 **NOT_TESTED** |

## D. Mandatory blockers for final P5-X

1. **Exact-head build:** latest #665 HEAD `74a2b0f…` does **not** equal W1 ELF build source `05d7ce4…`, even if executable code files compare identical. Rebuild/pin one *real* final-HEAD ELF + both app libs.
2. **Latest-head P05**: re-run both full input checks using this one final ELF, observe 12/12 FV Kernels, 12/12 FV BC, electron 8 BCs and unique Functor/Rate/Wall consumers in live Warehouse at the **same** exact HEAD. Existing detached observations are only `PASS_PROBE`.
3. **N1–N8 negative suite:** 8 groups × 2 cases = **16 actual Native fail-closed + exact error/log SHA + original SHA restore**. **0/16 qualify for current exact-head full matrix**; one detached S6-417 duplicate-O2p-time negative is useful evidence but cannot satisfy the matrix. Static/source model mutants are not Native tests.
4. **D8 complete:** current constructor, RF-off wall residual, and reduced-parent Maxwell seven-Transfer checks are real and valuable, but full original S6 coupled dynamic execution is not demonstrated.
5. **P5-X formal**: preserve same OCI/binary/source across all cases and negative jobs, original public/private rate byte custody, and `P3/P4=NOT_RUN` / `SCIENCE_HOLD`. Do not disable P05, use `dont_create_kernels`, or remove CI checks to get green.

**Independent re-verification:** Nine downloaded ZIPs, **96/96 fail-closed local integrity and evidence checks PASS**, including ZIP CRC+SHA, W1 TAR internal ELF + both app libraries, actual case log bytes, Warehouse lists and bounded D8 CSV/logs. Local reproducibility: `p5x_native_evidence_verify.py` SHA256 `57fafc8337b264386a56956db016ca57be44c7f4704d16aa73a469ef20c50e86`, detailed JSON SHA256 `a369b27f8862e80639c5fed745603b014bb691f268e2daf348b5bc09fbb7f500`. GitHub machine [companion receipt](./p5-x-native-evidence-integration-20261118.json).

**Outcome:** `P5_X_NATIVE_EVIDENCE_INTEGRATED=PASS` is a **documentation/evidence result only**. **`NEW_ONLY_S6_P2_FINAL=HOLD`** until the exact-HEAD binary/P05/N1–N8/D8 gates above are met; Native science `P3/P4=NOT_RUN`, `SCIENCE_HOLD`.