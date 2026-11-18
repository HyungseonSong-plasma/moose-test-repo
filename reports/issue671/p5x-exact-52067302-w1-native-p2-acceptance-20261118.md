# #671 P5-X — 최신 #665 HEAD 단일 W1 Native P2 / Warehouse / 16 negatives

> **P5_X_EXACT_HEAD_NATIVE_P2=PASS** · **P5_X_TYPED_WAREHOUSE=PASS_32_PER_CASE** · **N1_N8=PASS_16_OF_16** · **SCIENCE_HOLD**.
>
> 작성 2026-11-18 · 대상 [PR #665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) source HEAD `52067302d16074592503d0ef6b903cc344f55a08`; source tree `2720fa5272a5fa98001e8e444331397723fe7ccb`. 이 HEAD에서 **새 W1을 실제로 한번 빌드**했다. 이전 `74a2b0f`에서 빌드한 W1 결과를 최신 HEAD로 승격한 것이 아니다.

## W1 Source / Build

[GitHub CI #44345886330](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44345886330), job `134948028757` **SUCCESS**; [Artifact #14446611291](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44345886330/artifacts/14446611291). ZIP SHA256 `6d24d997075c76983b5d99fc28c3cfc0f9fae1a57ccc00c63af4d8697c83d676` (CRC PASS). Archive TAR SHA256 `e42e29529121e7312062fdbe39a6cb50881b6424fb7197b10a36be97a6bbca64`.

| 단일 빌드 구성요소 | 실제 바이트 SHA256 |
|---|---|
| `physics-opt` | `912b212c3c1849165ab3da13d758f5b3e101f5b6cb7e1e3f3820259f6080f7eb` |
| `libphysics-opt.so.0` | `61f66ec66843f1d51bd79ef7542197410bebf92487f2cff70e9e08f9e958da82` |
| `libphysics_test-opt.so.0` | `e9ad1adeb8fcba312cf836520927a3de3fc5ad986d35d50f6cfe5d114e825f0f` |

원본 ZIP/TAR/ELF 세 파일 바이트를 오프잡 재해시했다. 빌드 횟수 1, source/head/tree 고정, OCI `ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008` 고정.

## 동일 W1 실제 Native P2 / Typed 등록

[GitHub Actions #44347074110](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44347074110), job `134952233626` **SUCCESS**; [Artifact #14446522947](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44347074110/artifacts/14446522947). 원본 ZIP SHA256 `69273ea8c28b050240ced8e5a891686350a2588ecc283da09ecf216521a9dca2` (CRC PASS). `p05_negative_receipt.json` SHA256 `7291a18045a873277be9b5cc4068383ca3eee3652caaf75b14a2efc335fd0677`.

| 증거 | S6-417 | S6-941 |
|---|---|---|
| `--check-input` | exit 0, Syntax OK | exit 0, Syntax OK |
| `DDContinuityEq::checkIntegrity()` / P05 | PASS | PASS |
| Generated FV Kernel | **12/12** | **12/12** |
| Ion FV BC | **12/12** | **12/12** |
| Electron FEM BC | **8/8** | **8/8** |
| 등록 후 실제 name/type 이벤트 매칭 | **32/32** | **32/32** |
| 원본 11-layer 입력 / JSON / mesh SHA | PASS | PASS |
| N1–N8 독립 음성 케이스 | **8/8** | **8/8** |
| 원본 입력 SHA 복구 / 보호 EI 삭제 | PASS | PASS |

각 case에서 77개의 외부 C++ 등록 이벤트가 기록됐다. 생성 12+12와 전자 FEM BC 8의 이름/Factory를 **원래 W1 ELF를 변경하지 않고** 외부 `FEProblemBase::add*` 성공 후 계측으로 확인했다.

N1–N4는 실제 P05 중복/예상 외 소유권 검출(총 8), N5는 더 이른 이름 등록 충돌(2), N6–N8은 Chemistry 보존·초기조건 검증(6)으로 **16/16 의도한 비정상 종료 및 예상 오류 계열 PASS**. 16/16 전부를 P05 오류라 칭하지 않는다. 정상 입력을 변형하지 않고 독립 Scratch 복제에서 수행했으며 각 입력이 원상복구됐음을 SHA로 확인했다.

## 독립 Artifact 검증

원본 GitHub Artifact ZIP 2개 다운로드 후 ZIP CRC, W1 TAR 내 3개 ELF byte SHA, W1 identity/tree, P4-X 11-layer 입력 SHA, 두 case의 실제 typed 등록·정상 종료·음성 오류 분류·보호 Scratch 제거를 **174/174 PASS**로 확인했다.

- 검증 스크립트 SHA256: `8070a8d005795a3ee045591ebdccb0bacd8bb04f5e5c312a701b00a7569c878a`
- 검증 JSON SHA256: `5555b6c5b36490033dacf4bccc39f748ac72660e47d5bcacd06056d8ed1e18dc`
- 관련 원본 CI artifact 저장 기간 내 영구 증거로는 이 머신 판독 [Receipt](./p5x-exact-52067302-w1-417-941-typed32-n1n8-acceptance-20261118.json)가 남는다.

## Acceptance boundary

**요청된 exact-HEAD 단일 W1 → 두 case Native P2 → Warehouse 12+12+8 → 16개 음성 실행은 완료 및 PASS**. 이전 남은 `P5_X_STRICT_HEAD=HOLD`는 현재 대상 HEAD `52067302…`에 관해서는 **해소(PASS)**.

그러나 외부 계측은 등록 후의 `family/name/Factory` 추적이지 `TheWarehouse` 생성 완료 후 메모리 덤프가 아니다. `variable/sideset` 런타임 파라미터 메모리는 직접 캡처하지 않았고, 공개 Artifact에 원시 tracer 로그·전체 stdout/stderr도 없으므로 내부 로그 SHA를 독립 재계산하지 못한다.

구 W1(`74a2b0f`)에서의 [D8 bounded 3ns RF·Wall·Current·Poisson PASS](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44337988067)는 **새 `52067302` W1의 D8 시험을 대체하지 않는다**. 그러므로 `D8_EXACT_520_NEW_W1=KEEP_HOLD_NOT_RETESTED`, `P5_X_FULL_DYNAMIC=KEEP_HOLD`, `100us P3/P4=NOT_RUN`, `SCIENCE_HOLD`, 역사적 Hybrid `KEEP_HOLD`를 유지한다.

**보호 경계:** #665/main/PhysicsApp/P05/공유 CI/원본 11-layer 코드·데이터는 수정하지 않았다. 빌드·검증은 별도 one-shot 브랜치에서만 실행했고, Private EI 원본은 보호 Scratch에만 사용 후 삭제, 공개 Artifact에 포함되지 않았다.
