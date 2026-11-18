# P6-E2 — 17개 P6-0 독립 영수증 기반 Lane별 PASS / KEEP_HOLD·P7 인계 판정표

> **판정: `P6_E2_DECISION_TABLE=PASS_EVIDENCE_ONLY` / `P6_X=HOLD` / `P7_HANDOFF=READY_CONDITIONAL` / `P7_FINAL_ACCEPTANCE=HOLD` / `SCIENCE_HOLD`.**
> 본 판정은 실무용 모드 분리·병목·증거 인계 문서다. Native/Science 성공이나 PR 병합 승인이 아니다.

## 1. 동결 기준과 영수증 수

- **고정 PR:** [Draft #665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) HEAD `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f`, tree `10ab018235f047bf1abc250d3b18005b9156752a`; `main=ebcfd9e662bc40f0473d8da05da95d11b61789f8` (미병합).
- **상위 P6-0:** [17/24 source-bound 영수증 인덱스](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/007ce61d923f29eed2656fc8e4e66da138aa4427/reports/issue672/p6-0-parallel-receipt-index.json), blob `ab0ee7486d526e3e94195491c90c208689673cfa`.
- **재검증:** 16개 개별 GitHub 증거 파일의 실제 Git blob을 재확인, D1은 [Draft PR #684](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/684)와 [별도 P05 Native 독립 리뷰](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/684#issuecomment-6980545736)로 확인 → **기초 17/17 증거 존재**. 이것은 17개 Job의 Native PASS를 뜻하지 않는다.
- **E2 이번 산출:** P6-E2 증거 판정 문서 1건 작성. Coverage **기존 17 + E2 1 = 18/24** *(자료/의사결정 수준만)*; 실제 실행·통합이 남은 6개는 `D5, F4, I3, N2, N3, C3`.
- **과거와 현재:** 역사 #578/Hybrid P2, Public B 10-layer, P5 W1/W2/W3의 이전 소스 바이너리는 최신 exact-head New-only 11-layer 수용 판정과 절대 합산하지 않는다.

## 2. Lane별 최종 증거 범위 및 운용 판정

| Lane | 과거/현재 실측 | E2 판정 | 필수 차단 원인 | P7 인계 조건 |
|---|---|---|---|---|
| **Public B (역사 10-layer)** | 최신 HEAD Public B 417·941 `--check-input` 각각 exit 0/Syntax OK. #578 과거 성공 증거 별도 보존 | **PASS — HISTORICAL P2 ONLY** | New-only/과학 동등성 증거 아님 | 과거 원본·Log·ZIP SHA와 함께 read-only 기준 대조군으로 인계 |
| **Public D (11-layer 옵션 경로)** | #665 417·941 양쪽 e JSON Transport 누락으로 exit 1. #684에서는 그 누락 해소 후에도 Chemistry FV Source 생성 계약 미충족으로 **417·941 exit 1, P05 이전 실패** | **KEEP_HOLD — 현행 Native 실패** | FV Chemistry 계약·4개 Manual→Generated Owner·Electron 5/3/8 FEM BC·**100행 역사 Lookup vs 42행 준비 테이블** 권위 미확정 | D2 승인 → D4 바이트·단위·Consumer/Rate 보존 → D5 별도 417·941 Native/P05; #684 **병합 금지** |
| **FLOW D/Hybrid** | #665 기존 417 e Transport 누락 exit1, 941 fail-fast NOT_RUN. #684 별도 진단에서는 **417·941 P05 `ni_time` 중복 exit 1** | **KEEP_HOLD — 현행 FLOW** | Legacy ion Native 26과 Physics 생성 24가 동시에 Owner. Hybrid를 New-only로 위장할 수 없음 | F1/F2/F3 모드 분리; 역사 Hybrid는 근거 있는 KEEP_HOLD, 별도 New-only 26→0 승인 후 F4 양쪽 P2 |
| **ARCH Hybrid** | 현행 417·941 P05 `log_O2p/ni_time` 중복 거부. 과거 고정 소스의 H3 특정 P2 Job은 양쪽 Syntax OK이나 **해당 전체 Workflow 결론은 FAIL** | **KEEP_HOLD — 현행** / **PASS — 과거 PINNED P2만** | Hybrid Native26/Physics24 모드 충돌과 #541 권위 분리 | H1·H2·H3를 역사 Job 범위로 인계, 전체 Workflow/현행 ARCH PASS로 승격 금지 |
| **Ion-FVM 기존 두 Matrix** | 두 경로 모두 `RETIRED_GROUNDED_SHEATH_BCS` Python 입력 생성 단계에서 중단, Native 시작 전 | **KEEP_HOLD — PRE-NATIVE** | C2 Wall/Dielectric은 기존 Grounded Sheath와 물리적으로 비등가; 명시적 물리 승인 없음 | I1/I2 소스·오류 단계 인계, 승인된 P0/P2 전용 I3만 가능. 무승인 1ns·5ns·10ns 또는 150/200-step 금지 |
| **새 S6 New-only 417/941** | W2/W3 실제 Syntax OK 양쪽, Warehouse 12+12 및 P05 N1–N8 16/16 별도 영수증 존재. 그러나 W1 ELF 소스 `05d7ce4…` ≠ 최신 HEAD `74a2b0f…`, Warehouse와 음성도 서로 다른 Epoch | **HOLD — P5-X 공식 미수용** | 최신 exact HEAD 동일 ELF/앱 lib/OCI + P05 16개 음성 + D8 원형 RF 연동 미완 | P5-X 완전 PASS 후 N1 계약에 따라 N2 전용 Runner → N3 두 사례 Native CI |
| **Repository CI / CI Workflow** | `validate=PASS` (1566 passed, 13 skipped), `ci.yml`↔generated template 17-Job 바이트 동등. **Repository CI 전체 FAIL** | **PASS — validate/template만** / **HOLD — 통합** | D/F/H/I 실패 존속, PR 메타데이터 `edited`가 4개 고비용 Native Job을 재발화 가능; 자동 100us P3·150/200-step 위험 | C1+C2 결과로 C3 단일 Writer가 보호 조건·artifact fail-closed·template parity 보존, exact-head CI 재검증 |
| **증거 보관 E1** | 역사/최신 ZIP 11개 SHA+CRC, ELF+2 앱 라이브러리 출처 독립 작업자 검증 | **PASS — custody만** | E1 작업 브랜치가 PR665와 달라 전체 Cherry-pick/merge 금지. P6-E2가 11개 ZIP을 다시 모두 받은 것은 아님 | 결과·아티팩트별 exact SHA만 선택 인계, 소스/Runner 자체는 변경하지 않음 |

**KEEP_HOLD**는 숨긴 성공 또는 조용한 skip이 아니다. 현재 실패를 가시적으로 보존하고 향후 승인된 모드에서만 다시 검증한다는 운영 판정이며, 최종 CI 승인권자의 KEEP_HOLD 수용은 아직 별도로 필요하다.

## 3. 핵심 Native 실측 및 승인 경계

- **[공식 Repo CI #44297212655](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44297212655):** 전체 FAIL, `validate=1566 PASS/13 skipped`. Public B 417/941 P2 PASS; Public D 두 사례 e Transport JSON 오류; ARCH 두 사례 P05 `ni_time` 중복.
- **[FLOW #44297212567](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44297212567):** 417 실패, 941 조기 중단으로 미실행.
- **[Ion-FVM #44297212333](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44297212333):** 두 Matrix 모두 Native 전 `RETIRED_GROUNDED_SHEATH_BCS`.
- **[PR #684 별도 exact-source P2 #44314726088](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44314726088):** Source unit tests PASS이나 Public D 417/941과 FLOW 417/941 4/4 Native 실패. **[독립 통합 리뷰 결론: DO NOT MERGE](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/684#issuecomment-6980545736)**. Public D는 Chemistry 생성 전제 실패, FLOW는 P05가 의도대로 중복 Owner 거부. P05 완화 금지.
- **[P5-X 최신 수용 리뷰](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/671#issuecomment-6980120842):** 9 Artifact 및 96/96 교차 Assertion 완료는 **증거 취합 PASS**이고 최종 P5-X는 HOLD. 기존 W1 ELF SHA `cab62a4a9caa4d99a82564f31f915f1a7dc14565607712841123a30276d329bc`는 구 소스 `05d7ce4…`에 묶임. P5 N1–N8 × 2의 16개도 최종 HEAD에 자격 있는 검증은 **0/16**.
- **#535/#541:** 역사 10 Workflow 퇴역 승인 및 과거 수동 S6 Hybrid 400W/100us P3의 범위에 한정. Public D 신규 Transport 물리 의미, C2의 Grounded Sheath 대체, New-only 과학 P3/P4·자동 장시간 계산은 승인된 것으로 간주하지 않음.

## 4. 17개 원본 영수증: Source-bound 실제 Readback 목록

| Slot | Lane | 영수증 성격 | 범위·한계 | 원본 |
|---|---|---|---|---|
| P6-B1 | B | INDEPENDENT_HISTORICAL_NATIVE | Direct historical/current job log readback: both Public B 417/941 10-layer P2 exit0; historical D P2 PASS, current D FAIL; New-only not inferred | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/28920362d985f0b08d16f9325a6b857834ccf90b/reports/issue672/p6-b1-public-history-native-p2-receipt.json) |
| P6-D1 | D | INDEPENDENT_CANDIDATE | PR684 code candidate, 18-case CI green, unmerged; Native hold | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/684) |
| P6-D2 | D | INDEPENDENT_READONLY | Authority/auto-science/P05 audit PASS; new cutover approval HOLD | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/a02d2438005e8165321ec9f5bd807c41b8a51f7c/reports/issue672/p6-approval-auto-p3-p4-p05-risk-audit-20261118.md) |
| P6-D3 | D | INDEPENDENT_SOURCE | Original 100-row lookup and ion 3/3 coefficient SHA, 8/8 negatives PASS | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/d11451aa1dd4f4266205e3792561965d4881f8c6/reports/issue672/p6-d3-public-d-transport-lookup-unit-charge-original-sha.json) |
| P6-D4 | D | INDEPENDENT_SOURCE_DECISION_HOLD_NATIVE | PR684 four manual Transport owners cutover source checks 10/10; 100-row original vs CI prepared 42-row electron table byte identity split; Native P2 NOT_RUN, separate authority | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/c3bf3713c68d78b56ec5679cdc620b533b12216c/reports/issue672/p6-d4-public-four-transport-owner-decision.json) |
| P6-F1 | F | INDEPENDENT_DIAGNOSIS | FLOW 417 transport FAIL, 941 not run after early abort | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/issue-672-p6-f1-flow-dbase-early-exit-readonly-20261118/reports/issue672/p6-f1-flow-dbase-417-941-early-exit-newonly-separation.json) |
| P6-F2 | F | INDEPENDENT_SOURCE | FLOW e 5/3 energy and ion provider graph static PASS; candidate not Native | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/issue-672-p6-f2-flow-owner-5over3-20261118/reports/issue672/p6-f2-flow-transport-material-and-electron-5over3-owner-source-receipt.json) |
| P6-F3 | F | INDEPENDENT_OWNER_DECISION_KEEP_HOLD | FLOW Hybrid historical 26 Native owners preserved, Physics 24 generated conflict; KEEP_HOLD historical and conditional separate New-only 26->0; F4 Native NOT_RUN | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/49b3e1dc6ca04f5808cd5e447be5dd13f43e57e2/reports/issue672/p6-f3-flow-26native-vs-24generated-owner-decision.json) |
| P6-H1 | H | INDEPENDENT_READONLY | Retain historical Hybrid, modern ARCH KEEP_HOLD, historical compatible separately | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/issue-672-p6-h1-arch-hybrid-compatibility-20261118/reports/issue672/p6-h1-arch-historical-hybrid-compat-approval.md) |
| P6-H2 | H | INDEPENDENT_NATIVE_NEGATIVE | Both current ARCH cases real P05 ni_time fail, static 36/36 negatives | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/issue-672-p6-h2-arch-p05-20261118/reports/issue672/p6-h2-arch-p05-owner-negative.json) |
| P6-H3 | H | INDEPENDENT_HISTORICAL_NATIVE | Old pinned source P2-only 417/941 success; overall historical workflow failure; modern ARCH HOLD | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/issue-672-p6-h3-pinned-arch-p2-20261118/reports/issue672/p6-h3-historical-arch-p2-replay.json) |
| P6-I1 | I | INDEPENDENT_ROOT_CAUSE | Two matrix Actions job log backtraces independently confirm Python RETIRED_GROUNDED_SHEATH_BCS before input/Native/timesteps, KEEP_HOLD | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/dce2d02306377b3c4b056b10cb7e3a0b70ad6f1c/reports/issue672/p6-i1-retired-grounded-sheath-caller-chain.json) |
| P6-I2 | I | INDEPENDENT_ANALYSIS | C2 adjacent-field sheath differs from grounded conductor; no equivalent substitution | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/9d5e5762b53574e41e65850fc217ddf9a1572e11/reports/issue672/p6-i2-c2-wall-dielectric-vs-grounded-sheath-physics-contract.json) |
| P6-N1 | N | INDEPENDENT_DESIGN | New-only CI contract G0-G6 documented; N2 not implemented | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/4e486f3e833693b289f9e7f27329fa3c17dabade/reports/issue672/p6-n1-newonly-native-p2-contract.json) |
| P6-C1 | C | INDEPENDENT_SOURCE | ci.yml/template exact SHA equality, 17 jobs, edit-only trigger/native costs gap | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/c0db8aa2fca47ffe5fc6045872d1b7a5351de5b8/reports/issue672/p6-c1-ci-template-trigger-protection-readonly-audit-20261118.json) |
| P6-C2 | C | INDEPENDENT_POLICY_AUDIT | 12/12 source policy predicates: automatic 100us and 150/200 steps trigger risks, P05 conditional coverage, #535/#541 approval; C3 single-writer HOLD | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/0b89891cb7915e5c94c4ca6fad559b66aa78abca/reports/issue672/p6-c2-approval-autostart-p05-risk-gates.json) |
| P6-E1 | E | INDEPENDENT_CUSTODY | 11 artifact SHA+CRC, binary sources; E1 receipt branch diverged from PR665; never whole-merge | [원본 영수증](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/c54ad7fccf6357ceded8d2af28dfebc54d55e31f/reports/issue672/p6-e1-ci-artifact-binary-source-custody-20261118.json) |

`P6-D1`의 원본 링크는 **합병되지 않은 Draft PR #684**이며, 다른 16개와 달리 단일 JSON 파일 영수증으로 세지 않는다. 해당 PR의 exact-source Native 리뷰가 candidate의 수용 범위를 결정한다.

## 5. 미해결 6개 — 다음 실행 의존성

| 남은 Slot | 실행 전제 | 필요 증거 / P7 인계 상태 |
|---|---|---|
| **D5** | D2의 Public 100/42 행 권위·Physics Chemistry FV Source 계약 결정, D4 완전 안전 이관 | 417·941 현행 승인 모델 동일-HEAD Native P2/P05 PASS, 실패 시 KEEP_HOLD |
| **F4** | F3 역사 Hybrid vs 승인 New-only 모드 결정, legacy ion 26/Physics24 Owner 중복 제거 계약 | 417·941 개별 Native, 실제 P05·Owner·모든 Rate/5:3/Wall 보존 |
| **I3** | C2와 Grounded Sheath 비등가를 감수할 새 물리 승인 또는 KEEP_HOLD 공식화 | 승인된 P0/P2만. Native 시간적분 P3/P4 자동 실행 없음 |
| **N2** | **P5-X 최종 PASS**, N1 G0–G6 설계, C3 정책 경계 | 독립 New-only CI Runner: 1 ELF+2 .so+OCI/exact HEAD, Private EI, Warehouse/P05, 별도 read-only 417·941 |
| **N3** | N2 Runner·P5-X PASS | 최신 exact-head 두 사례 실제 CI/Artifact/EXIT/SHA/P05/복원 독립 검증 |
| **C3** | C1/C2 정책·D/F/H/I 승인 결정·New-only 수용 경계 | 오직 통합 Owner가 `ci.yml` 및 템플릿 동시 변경, metadata-only 비용 Guard·필수 Artifact·P05 설정 보호, 전체 CI 재실행 |

E2 문서는 이 표의 **증거 인계 작성**만 완료하며 D5/F4/I3/N2/N3/C3를 실행·승인하지 않는다.

## 6. P7 인계 수용 계약

**현재 `P7_HANDOFF_DOCUMENT=READY`이고 `P7_FINAL=HOLD`.** P7은 다음 독립 증거를 요구한다.

1. Draft #665 새 HEAD 변화 감지 후 **exact HEAD+Tree / OCI·MOOSE vendor / 단일 실제 ELF+두 앱 라이브러리** SHA 고정. 다른 소스의 기존 ELF 재사용 금지.
2. **417·941 각 11-layer 원본/변환 SHA, JSON, main Plasma mesh, Maxwell include, protected Original EI 5개/case**를 동일 소스·실행 단위로 재검증. 100행 Public D/42행 New-only Electron Lookup 혼합 금지.
3. 두 사례 동일 실제 ELF의 Native `--check-input` exit 0 / Syntax OK, **Warehouse 12 ion FVKernel + 12 ion FVBC / electron FEM BC 8**, 원래 26 Native ion owner 0 및 P05 단일 Owner/Charge·Source·Poisson·Wall·Surface Current 소비자 검증.
4. **P05 음성 N1–N8 × 417/941 = 16/16**을 *최종 동일 HEAD·ELF*로 FAIL-CLOSED 재실행, Scratch 원상 SHA/Private EI 삭제/Artifact SHA 보존.
5. **D8 실제 full S6 RF Maxwell child/7 Transfers 및 late-bound 소비자** 계약 확인. 현재 각각의 reduced parent/Poisson/FaceArg 부분 실행만으로 full coupled RF까지 승격 금지.
6. Public B/D, FLOW, ARCH, Ion-FVM 각 **승인된 Native PASS 또는 승인권자에게 전달된 explicit KEEP_HOLD**, 역사적 고정 버전과 현대 P05 중복/전처리 오류를 분리.
7. C3 전체 CI·생성 템플릿의 SHAs 일치, 17 Job trigger 검증, 자동 P3/P4 또는 100us/150·200-step 발화 0, `dont_create_kernels`/P05 bypass 0, Private EI 유출 0, 필수 Artifact 존재 및 SHA 확보. 최종 P6-X 통합 판정 후 P7 #673에서 별도 DoD 평가.

## 7. 다음 단계 / 금지사항

- **즉시 병렬 가능한 작업:** D2의 원본 테이블 권위 및 Chemistry 계약, F3 기반 New-only 이관 설계, I3의 별도 물리 승인 요청, P5-X 최종 HEAD 바이너리·16음성·D8 보강, C3의 변경 전 안전 설계.
- **직렬 통합:** P5-X → N2 → N3 및 D5/F4/I3 승인 결과 → C3 단일 Workflow Writer → exact HEAD CI → P6-X → **P7 실증·판정**.
- **금지:** PR #684 또는 #665의 자동 병합, `main` 병합, 오래된 영수증의 현재 HEAD PASS 승격, 오류 Lane의 skip/`dont_create_kernels`/P05 완화, 승인 없는 기존 100us 과학 P3/P4와 Ion-FVM 150/200-step 자동 실행, 보호 EI 원문 Artifact/GitHub 공개.

**최종 상태:** `P6_0=PASS_17_RECEIPTS`, `P6_E2=PASS_DOCUMENT_ONLY`, `P6_X=HOLD`, `P7_HANDOFF=READY_CONDITIONAL`, `P7_FINAL=HOLD`, `SCIENCE_HOLD`. Markdown과 기계 판독 JSON은 서로 같은 고정 HEAD/판정 계약을 사용하며, 별도 브랜치의 증거 파일 외에 Production/CI/원본 변경 없음.
