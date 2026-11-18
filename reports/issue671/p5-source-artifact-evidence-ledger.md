# #671 P5 — Source / Artifact 증거 대장 (2026-11-18)

> **문서 상태:** `EVIDENCE_LEDGER_DRAFT` · 최종 P5-X 판정 영수증 아님  
> **검토 기준:** Draft PR [#665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665), 관측 HEAD `05d7ce4eceb81769cb2f0146c51535fc35e74ac1`. PR은 OPEN/DRAFT, `main`에 미병합.  
> **범위:** S6-417/S6-941 실제 New-only 입력, 기존 Source·CI Artifact·영수증, 공통 바이너리, 보안 EI rate, P05 및 음성 테스트. 이 문서의 기존 CI 결과를 현재 HEAD의 자동 수용으로 승격하지 않는다.

## 1. 판정 규칙

- **PASS_SOURCE:** 실제 원본/변환 `.i`, JSON, mesh, 공개 DB의 정확한 SHA와 Source 계약을 확인한 상태. **PASS_NATIVE**가 아니다.
- **PASS_PROBE:** 별도 프로브 HEAD·빌드 바이너리에서 실행/관측된 결과. 해당 커밋·바이너리·case·log 범위에서만 유효하다.
- **PASS_NATIVE_FINAL:** 최종 고정 PR #665 HEAD, 단일 바이너리·앱 라이브러리, 격리된 417/941 Scratch, 보안 rate stage, P05 실물 inventory, 음성 job, D8를 **모두 동일 실행 계약으로 충족**한 경우에만 가능하다.
- **HOLD:** 미실행, 서로 다른 HEAD/바이너리 혼합, Artifact 누락, 충돌 미해소, 반례 또는 증거 부족. CI Workflow `success`와 개별 `physics-opt --check-input`의 exit 0은 별개다.
- **FAIL:** 같은 최종 HEAD에서 실행한 게이트의 필수 조건 위반이 실제 관측·재현된 경우. 과거 프로브 FAIL은 과거 프로브로만 분류한다.
- `SCIENCE_HOLD`는 Source/P0/P1/Native P2가 통과하더라도 **수치 동등성(P3/P4)**이 별도 수용되기 전까지 유지한다.

## 2. Source / Artifact 영수증 대장

| 계층·게이트 | 근거 Run / Artifact | ZIP SHA-256 (GitHub digest) | 증명 범위·시점 | 현재 사용할 판정 |
|---|---|---|---|---|
| P1-0 immutable 417·941 최종 Hybrid 11-layer | [Run 44182628032](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44182628032) / [#14372278070](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44182628032/artifacts/14372278070) | `97333b09ca3017edb04a35b2ceb82398894ddb61f256fee10e4e8cb7ede623db` | 두 사례 11개 원본 입력과 Native old-owner 블록 기준점, PR 최초 Source HEAD `9c15a4f0…` | **PASS_SOURCE_BASELINE** |
| P2 source-only 26→0 / JSON / layer-11 / Maxwell | [Run 44199587771](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44199587771) / [#14380831538](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44199587771/artifacts/14380831538) | `3e6468c6fa96c41387415d88b9f9b7b2d16bdc622ea469e1bb88840132f33683` | 각 사례 기존 ion Kernel 14 + FVBC 12 퇴역, JSON/전자 테이블 및 child·mesh staging; [P2 receipt](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/05d7ce4eceb81769cb2f0146c51535fc35e74ac1/reports/issue668/p2_production_newonly_integrated_receipt.json) | **PASS_SOURCE_ONLY** |
| P3-X electron 10 old-owner 퇴역 | [Run 44256823392](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44256823392) / [#14405784430](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44256823392/artifacts/14405784430) | `9e6e8a646e3c3706e56b681c2a272081fbb55aaf74c4914f52c9db37507d0de6` | 417+941 22/22 staged layer SHA, old ion+electron 72/72 삭제 블록 SHA; [P3-X receipt](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/05d7ce4eceb81769cb2f0146c51535fc35e74ac1/reports/issue669/p3-x/verification_receipt.json) | **PASS_SOURCE_ONLY** |
| P4-X 7개 duplicate provider cutover | [Run 44274320806](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44274320806) / [#14414026909](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44274320806/artifacts/14414026909) | `6773dfa54bd1a77c908831be3edd6a93699152f5879e96f6bf3db435df431540` | [PR #677 병합](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/677); C0의 6 ion transport outputs 삭제, 3 old wall + 3 old current Material 퇴역, `carrier_one` 보존. [인계](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/670#issuecomment-6974325760) | **PASS_SOURCE_CUTOVER**, 전체 P4-X/D8 **HOLD** |
| protected EI rate custody | [Run 44268361259](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44268361259) / [#14411626010](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44268361259/artifacts/14411626010) | `195210cc96c80a096103c855e31804e2a0fd52ed9f31a64cde23f9dc773f6127` | 6개 원본 rate SHA 검증, 417/941 각 5개 `/dev/shm` 0700/0600 Stage 후 삭제. **Artifact는 SHA/count-only.** [보안 receipt](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/05d7ce4eceb81769cb2f0146c51535fc35e74ac1/reports/issue671/p5_a3_protected_original_ei_scratch_handoff_receipt.json) | **PASS_SECURE_HANDOFF**, 향후 Native 보호 실행에서 **재-stage 필요** |
| parent plasma main mesh | [Run 39575896519](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39575896519) / [#12349847563](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39575896519/artifacts/12349847563) | `f07f082267e159ad87ce1cdab79c95fcd8d78cdc6ed1a6168c4fa09ae1f132a2` | canonical `graded_level_1.msh` → S6 parent `baseline_plasma_plus_unstructured_cover_plus_wafer.msh`, SHA `ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc`; **Maxwell child qvt.msh와 다름** | **PASS_SOURCE_MESH_PIN** |
| P5-0 one-build executable + app shared libraries | [Run 44279232578](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44279232578) / [#14416831615](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44279232578/artifacts/14416831615) | `b97c997ac0c665628c1b3eace3bd577496bbf4333f7fbff74dbe12700aa575c8` | **이전** PR665 HEAD `3bf1777ee4c1f15ee5aa6493745b415ad5e67c81`의 한 차례 OCI 빌드, `physics-opt` 실물 SHA `bb55d25bbd8505d83c3f29ab1cb6478845d94f627548014c230375926cf335b0`, `.so` 2개 포함, isolated `--version` exit 0 | **PASS_P1_PREVIOUS_HEAD**, **HOLD_FINAL_HEAD_BINARY** |
| Native P05 live Warehouse probe, **별도 PR** | [Run 44280359966](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44280359966) / [#14417221187](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44280359966/artifacts/14417221187) | `edd8569834038cce51f7a1e13130c48bc76e4de4b6fac62d40cb5bce1323401b` | [Draft PR #678](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/678) HEAD `9e9b4f5ddb99bcbbf8c31746d7331587c9885a3f`; 417·941 각 live ion FVKernel 12 + FVBC 12, exit 0, P05 음성 1건 exit 1. 프로브 전용 binary SHA `65dcb77a7483e9a3861e8c1bfbe2413daec739e38240efa57d0a501dd1a36765` | **PASS_PROBE_ONLY**, **HOLD_CURRENT_PR665_ACCEPTANCE** |
| Wall 단일 구현 / 빌드 검사 | [Run 44281956063](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44281956063) / [P1 #14417278324](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44281956063/artifacts/14417278324) | `89a5d7ce57793d3bbbac8433c4618ae77b03577e34109c9b70d4ccc76cc1a655` | [PR #679 병합](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/679); old `PhysicsIonWallFluxMaterial` 코드와 `IonWallC2Detail` 제거, `IonWallFluxMaterial` 단일 등록/614 pytest + P1 빌드. [완료 receipt](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/05d7ce4eceb81769cb2f0146c51535fc35e74ac1/reports/issue633/ion_wall_single_factory_completion_receipt.json) | **PASS_WALL_SOURCE_AND_BUILD**, **HOLD_NEW_HEAD_NATIVE** |

추가 기록: [P5-E1 417 full custody](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/671#issuecomment-6973013136), [P5-E3 negative aggregation](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/671#issuecomment-6972935500), [P5-E4 cross-HEAD audit](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/671#issuecomment-6972956001), [P5-N6 Source/Rate 42개 변이](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/671#issuecomment-6972910897).

## 3. 병합 경계 및 역사적 판정 정정

1. [#674 P2](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/674), [#675 P3-X](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/675), [#676 protected EI helper](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/676), [#677 P4-X collision cutover](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/677), [#679 single Wall Factory](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/679)는 **Draft #665 브랜치에 병합**. `main` 수용을 의미하지 않음.
2. [#678 P05 probe](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/678)는 **미병합 Draft**. Warehouse 12+12 관측은 유효한 독립 실행 증거이나 현재 HEAD `05d7ce4…`의 최종 P5-B2/C2/E4 판정은 아님.
3. 과거의 `IonWallFluxMaterial` Factory **미등록 주장 철회됨**. 확인된 현행 `physics_app/src/functormaterials/IonWallFluxMaterial.C` Git blob `c965e1c2de9d1ba8eec6f3180c9eaeb5ca324fde`는 `registerMooseObject("PhysicsApp", IonWallFluxMaterial)`를 포함; old `PhysicsIonWallFluxMaterial.C`는 최신 HEAD에서 없음. **런타임 과학 검증과 분리.**
4. 과거 `P5_0_BINARY=BLOCKED_NOT_BUILT`는 로컬 도커 부재에 한정된 과거 진단. OCI GitHub Actions에서 **이전 HEAD** 실물 ELF + 앱 공유 라이브러리 빌드/실물 바이트 검증은 PASS. **최신 HEAD용 단일 재사용 바이너리의 동일성은 새로 고정**해야 함.
5. 이전 Native `--check-input`의 누락 main mesh / 공개 neutral DB / private EI rate **exit 1**은 해당 이전 프로브의 실행 결과. 후속 보안 Rate staging 및 mesh source pin 성공을 **최종 Native exit 0**으로 소급하지 않는다.
6. P5-N6 독립 42/42 변조 **정적 거부**는 C++ Native 42/42 FAIL-CLOSED가 아니다. `hasSpeciesSource`는 부분 반응 채널 누락을 완전히 보장한다고 입증되지 않았으며, case별 필수 EI/H25 채널 closed-set 계약과 실제 Native 음성 검증 필요.

## 4. 현재 HOLD 및 P5-X 인계

| 필수 수용 게이트 | 현재 입증 상태 | 남은 증거 |
|---|---|---|
| 원본 Hybrid 11-layer / 파일·블록 SHA | **PASS_SOURCE** | 최종 변경 후 Source 매핑과 diff |
| Production New-only P2 ion 26→0 / P3 electron 10→0 / P4 duplicate 7 edits | **PASS_SOURCE** | 최신 HEAD 실행의 417·941 final Scratch SHA와 P0 |
| 보안 EI Rate SHA/Stage + main/child mesh | **PASS_SOURCE / PASS_SECURE_HANDOFF** | 최종 `--check-input` 실행 컨텍스트에서 보안 단계 수행·정리 영수증 |
| 단일 Wall Factory P1/빌드 | **PASS_SOURCE_AND_BUILD** | 최신 HEAD 최종 binary/artifact identity |
| 공통 P5-0 `physics-opt`+앱 `.so` | **PASS 이전 HEAD**, **현재 HEAD HOLD** | 현 HEAD+tree, OCI/vendor, actual ELF/`.so` 바이트, digest readback |
| S6-417/941 real Native `--check-input` | **PASS 별도 프로브**, **현재 HEAD HOLD** | 같은 HEAD/바이너리의 두 독립 case exit 0, full logs, SHA |
| ion 12 Kernel +12 BC / electron BC 8 / electron Functor 2 | **ion 12+12 PASS 별도 PR678 프로브**, **현재 HEAD HOLD** | 실제 현재 HEAD Warehouse/P05 목록과 single owner 증거 |
| D8 Maxwell/neutral/RF/Poisson/Wall 동적 소비자 | **HOLD** | live lookup/caller/Field/FaceFunctor 접근성 로그 |
| N1–N8 S6-417/941 의도적 FAIL / SHA restore | **정적 Source 모델 PASS**, **Native matrix HOLD** | 16개 이상 개별 mutant Native job의 exact error/exit/restore |
| Same HEAD + binary across 정상 417·941·음성 | **HOLD** | 공통 `source_head`, `binary_sha256`, 동일 OCI와 `lib` 의존성 |
| Native scientific P3/P4 결과 동등성 | **NOT_RUN / SCIENCE_HOLD** | 별도 scientific acceptance |

**P5-X 최종 단일 Writer만** 게이트 수용값을 확정하고 #671 본문/통합 브랜치를 갱신한다. 소스/아티팩트 영수증의 존재만으로 Native P2, D8 또는 science를 PASS로 처리하지 않는다.

**연결 문서:** [P5 최종 판정 양식](./p5-final-acceptance-form.md) · [기계 판독형 증거 인덱스](./p5-evidence-gate-index.json)

## 5. W1 최신 P5-0 바이너리 영수증 보강 — 2026-11-18 (W8 완료 이후 P5-X handoff)

> **W8 상태는 DOCUMENTATION_COMPLETE.** 아래는 기존 W8 출력을 폐기하거나 변경 게이트를 자동 PASS시키는 자료가 아니라, **P5-X가 소비할 신규 W1 검증 Artifact**이다.

- [**W1 CI #44293156216**](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44293156216) / [**Artifact #14422701532**](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44293156216/artifacts/14422701532), GitHub digest·독립 다운로드 ZIP SHA-256 **`ce50a51f2ab565b5dc6aced272adcf12f1075f7593417c603ce05274c8291c18`** (1,375,989 B), CRC PASS.
- **빌드 source HEAD** `05d7ce4eceb81769cb2f0146c51535fc35e74ac1`, tree `0385fbf71ef384bbad02a4222f2e799deb02b9a6`, OCI `ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008`. Build count 1, `make -C physics_app -j2 app_non_unity_dirs='%/utils'`.
- ZIP member `physics-opt-and-app-libs.tar.gz` (SHA-256 `705e1f3fa58c4da3c1d76cbca7f2a761045f8f46ee6f54d3391aeaf5ab62033c`), **실제 tar member 바이트 직접 재해시**:
  - `physics-opt` 67,368 B · `cab62a4a9caa4d99a82564f31f915f1a7dc14565607712841123a30276d329bc` (executable).
  - `lib/libphysics-opt.so.0` 4,869,600 B · `3274751989604b06e7e7e677435b16c874388a4f7b8735b059eafc605fbb7e51`.
  - `lib/libphysics_test-opt.so.0` 105,984 B · `86aa0d4ebe18d731e7e052f5ad62594b1a3b48074f848693b0958f728b61ba80`.
- Build log SHA `5bdda6ecfdcb2b8da8e6cd066f427cecfea1f33cdbbc5a483039cf521928b3c8`, toolchain log SHA `069772ddb3e8df032f756ae6e78329deb4125790fd612f90797933c8c55158c1`. `identity.json` / `sha256sums.txt` / TAR member 실물 값 일치. Artifact에 raw private EI rate 없음; MOOSE vendor system libraries는 OCI에서 공급.
- **정확한 증거 수준:** `W1_P5_0_BINARY_AND_APP_LIBRARIES=PASS_SHA_VERIFIED_FOR_05d7_HEAD`; **Native check-input NOT_RUN**, 두 case Warehouse 통합·N1–N8·D8 NOT_VERIFIED. W1은 Native P2 성공 근거가 아님.
- **Source HEAD drift:** 영수증 보강 시 PR #665 HEAD가 `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f`로 이동함. `05d7…`→`74a…` compare: 6 commits, 변경 경로는 `tests/test_issue633_s6_scratch_ion_retirement.py` 한 개. C++/배포 Runner 변경은 diff에서 관측되지 않았지만 **엄격한 final `source_head` 일치 조건은 충족하지 않음**; P5-X는 재고정·재검증 또는 승인된 동일성 계약을 별도 증빙해야 함.
- **P5-X 남은 필드:** 최종 HEAD/tree/ELF·lib SHA, 두 Native 417/941 성공 exit/log/Artifact, 실물 P05(ion 12+12 및 electron), D8 동적 호출자, N1–N8 정확한 실패·원상복원 및 정상/음성 동일 HEAD/바이너리. Native 과학 P3/P4는 계속 `SCIENCE_HOLD`.
