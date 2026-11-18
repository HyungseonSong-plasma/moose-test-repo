# #671 P5-X — 최신 PR #665와 W1·Warehouse 최종 게이트 판정 (2026-11-18)

> **결론: `P5_X_EVIDENCE_INTEGRATED=PASS`; `W1_RUNTIME_RELEVANT_SOURCE_BLOBS=PASS`; `P5_X_STRICT_FINAL=HOLD_EXACT_CURRENT_HEAD`; `SCIENCE_HOLD`.**
>
> 본 문서는 현재 PR HEAD와 W1의 증거 정합성을 독립 재검사한 **증거 통합**이다. 새 PhysicsApp 빌드·Native/과학 실행 또는 기존 수용 조건의 완화가 아니다.

## 1. 버전·원본의 연결

| 증거 항목 | 고정 값 및 판정 |
|---|---|
| 현재 [Draft PR #665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) | `52067302d16074592503d0ef6b903cc344f55a08`; tree `2720fa5272a5fa98001e8e444331397723fe7ccb` |
| 단일 W1 빌드 source | `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f`; tree `10ab018235f047bf1abc250d3b18005b9156752a` |
| [커밋 비교](https://github.com/HyungseonSong-plasma/moose-test-repo/compare/74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f...52067302d16074592503d0ef6b903cc344f55a08) | `ahead=4`, `behind=0`, 변경 파일 정확히 2개 |
| 변경 파일 | `.github/workflows/ion-fvm-hybrid-staged-dt.yml`, `tests/test_issue633_newonly_run_species_schema.py` |
| 실행 의미 관련 Blob SHA | `DDContinuityEq.C`, `Chemistry.C`, `IonWallFluxMaterial.C`, `FVLogMolarDielectricFluxBC.C`, P4-X retire helper, 보호 EI guard, New-only preparation **7/7 byte-identical** |
| HEAD 식별자 일치 | **아니요 — strict exact-HEAD는 HOLD** |

해당 두 변경은 오래된 Ion-FVM Hybrid CI를 New-only source P0 경로로 바꾸고 회귀 테스트를 확장한다. PhysicsApp C++ 및 해당 준비/소유권 소스는 W1 빌드 이후 변경되지 않았으므로 **기존 W1 증거의 해당 물리 구현에 대한 적용 가능성**은 뒷받침된다. 그러나 **동일 소스 HEAD에서 생성된 바이너리의 인증**은 다른 주장이다. 현재 #665에서 재빌드하지 않았으므로 과거 W1의 PASS를 strict current-head P5-X PASS로 승격하지 않는다.

## 2. 단일 W1 실제 실행 파일

[W1 Build #44319316180 / Artifact #14435245012](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44319316180/artifacts/14435245012)를 원본 ZIP→TAR→ELF 3파일까지 재해시하고 ZIP CRC를 검사했다.

| 파일 | 실제 바이트 SHA-256 |
|---|---|
| `physics-opt` | `1bdc85c65f5847ae58d51c76f89f8e67c67291dc9b5ee842bcbab98c4a71befa` |
| `libphysics-opt.so.0` | `b107698dfc7539237cd194331e306efd28f3fba7bc7e0b958f4f8dd2165f67bd` |
| `libphysics_test-opt.so.0` | `bd1e0626a5e6682ffdda66fa6e1589f3f0d975a66aa9f79b964efeb1d84924a6` |

ZIP SHA-256 `b1f2dea2ab3d03b3c640260ce4fbdab72b2497a3d1faa24c54106e5f5847d4cd`; TAR SHA-256 `12f198cd17101b23b67a61a2fe95247af9c4c860d36b04ebf16b8dc91d4dadeb`. 동일 고정 OCI 사용, 다른 빌드의 바이너리 SHA 혼합 없음.

## 3. Warehouse 계측: 기존 HOLD를 해당 W1 범위에서 해소

[Native Run #44340416703 / Artifact #14444615886](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44340416703/artifacts/14444615886): CI 성공. ZIP SHA-256 `4910a1df8547b796be19623b903b3932640ec64a9facf7770494fa6da3870841`, CRC PASS; 실제 수집된 `p05_negative_receipt.json` SHA-256 `99e0c121a30fc77e43d0fb693f8825941afc542db709c961f95763f09dca06ca`.

| Native 검증 | S6-417 | S6-941 |
|---|---|---|
| 원본 W1 `--check-input` / P05 | **PASS, exit 0** | **PASS, exit 0** |
| FV ion Kernels | **12/12** | **12/12** |
| FV ion BC | **12/12** | **12/12** |
| electron FEM BC | **8/8** | **8/8** |
| 이름/Factory post-registration 실제 관측 | **32/32** | **32/32** |
| 전체 등록 이벤트(선택·비선택 포함) | 77 | 77 |
| N1–N8 실제 음성 거부 | **8/8** | **8/8** |
| 원본 staged input SHA 복구 | PASS | PASS |
| 보호 Private EI Rate tmpfs cleanup | PASS | PASS |

N1–N4는 P05, N5는 조기 등록 중복, N6–N8은 Chemistry 검증 실패다. 16개를 모두 P05 거부로 기록하지 않는다. 실제 상세 name/Factory/variable **출처 구분을 포함한 64행**은 [P5-X typed inventory receipt](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/9b7a55240880a178aa102483700746d7cd464db7/reports/issue671/p5x-w1-real-typed-12k-12fvbc-8fembc-417-941-receipt.json) 참조.

**증거의 한계:** 이 계측은 W1 바이너리를 변경하지 않고 `FEProblemBase::addFVKernel/addFVBC/addBoundaryCondition` 성공 이후 등록을 기록한 것이다. 직접 `TheWarehouse` 메모리 덤프 또는 런타임 파라미터의 variable/sideset 캡처는 아니다. Runtime variable/sideset 연관은 C++/JSON 소스 검증에 의존한다. Raw trace·전체 stdout bytes는 Artifact에 포함되지 않아 내부 로그 SHA를 off-job으로 다시 계산할 수 없다. 이 제한을 숨겨서 '원시 Warehouse 덤프 확보'라 하지 않는다.

## 4. D8 결합 검증 범위

기존 [D8 RF + Wall/Surface Current + Poisson CI #44337988067](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44337988067)과 [증거 receipt](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/d9e3452cebec800aaec65cf557891ba1f164c49b/reports/issue671/d8-rf-wall-poisson-actual-417-941-bounded-3ns-20261118.json)에 따르면, 동일 W1로 실제 원형 S6 Maxwell child·7 Transfer·Wall/Surface Current/Poisson 적분 관측이 417/941 모두 3 ns bounded 실행에서 PASS다. 이는 **100 μs 과학적 동등성 또는 same-run 직접 `computeQpResidual()` 계측**을 증명하지 않는다. 해당 RF Artifact 자체를 이번 통합에서 새로 재해시한 것은 아니며, 이전 검증된 영수증을 참조했다.

## 5. P5-X 단일 최종 수용표

| 게이트 | 판정 | 경계 |
|---|---|---|
| 현재 HEAD와 기존 W1 실행 의미 소스 바이트 | **PASS** | 일치한 관련 Blob 7/7 및 전체 diff 2파일 |
| current-HEAD와 W1 build HEAD의 strict identity | **HOLD** | `5206730… != 74a2b0f…` |
| W1 Native 417/941 clean P2 | **PASS** | `74a2b0f` 기준 |
| Typed FV 12+12 및 electron FEM 8 | **PASS** | W1 실제 등록 32/32 × 2 사례 |
| W1 N1–N8 | **PASS** | 16/16 의도한 Native 실패 |
| D8 원형 RF·Wall·Current·Poisson 결합 | **PASS_BOUNDED** | 동일 W1 3 ns |
| **P5-X strict current-HEAD 최종 수용** | **HOLD** | 520 HEAD의 실행 파일이 아님 |
| **New-only S6 P2 최종 수용** | **HOLD** | source/ELF exact-HEAD 분리 |
| 100 μs P3/P4 과학 | **NOT_RUN** | 별도 승인 필요 |
| 기존 Hybrid | **KEEP_HOLD** | P05/역사적 승인 경계 유지 |

**다음 단일 게이트:** `52067302…`에서 W1 실행 파일·앱 라이브러리 2개를 한번 빌드해 SHA를 고정하고, 동일 새 W1에서 417/941 clean Native P2 + 32×2 typed 등록 + 16개 음성 테스트를 다시 source-bind한다. 아니면 **동일 HEAD의 대체 수용 규칙을 별도로 명시 승인**받아야 한다. 이 문서 자체는 exact-HEAD 요건을 변경하지 않는다.

보안 및 변경 범위: `main`, PR #665, 원본 11-layer, `physics-opt`, 원본·보호 EI Rate, P05 guard, shared CI는 변경하지 않았다. 본 브랜치는 증거 문서만 추가했으며 자동 장시간/과학 실행을 시작하지 않았다.

[기계 판독 통합 증거](./p5x-520673-w1-warehouse-evidence-integration-20261118.json)
