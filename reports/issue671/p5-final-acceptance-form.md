# #671 / P5-X — S6-417·941 최종 수용 판정 양식

> **양식 버전:** `p5-final-acceptance.v1` · **상태:** `DRAFT / NOT_FINAL`  
> **작성 기준일:** 2026-11-18 · **검토한 현재 PR #665 HEAD:** `05d7ce4eceb81769cb2f0146c51535fc35e74ac1`  
> **중요:** 아래 `[증거 대기]`는 자동 PASS가 아니다. 실제 최종 실행 근거가 없는 항목은 `HOLD`로 유지한다. 과거/별도 PR의 성공은 `PASS_PROBE`로만 참조한다.

## A. 실행/수용 기준 고정

| 필드 | 최종 입력값 | 검증 요구 |
|---|---|---|
| Review/merge 대상 | Draft PR #665 | 현재 HEAD 재조회·고정 |
| **Final source commit SHA** | `[최종 단일 HEAD 40자리 — 증거 대기]` | 417·941·N1–N8 동일 |
| **Final Git tree SHA** | `[40자리 — 증거 대기]` | exact checkout, clean tree |
| Current review snapshot | `05d7ce4eceb81769cb2f0146c51535fc35e74ac1` | 비교용; 빌드 identity 아님 |
| Build workflow/job/run | `[Run ID / Job ID / URL]` | 실제 한 차례 빌드/P1 |
| OCI immutable digest | `[sha256:...]` | vendor/compiler/MOOSE label 재검증 |
| Compiler/MOOSE/METHOD/flags | `[증거 대기]` | source-bound 로그·영수증 |
| **실제 physics-opt SHA-256** | `[64 hex — 증거 대기]` | 실행 파일 원본 바이트 재계산 |
| `libphysics-opt.so.0` SHA-256 | `[64 hex — 증거 대기]` | 앱 로더로 확인 |
| `libphysics_test-opt.so.0` SHA-256 | `[64 hex — 증거 대기]` | 앱 로더로 확인 |
| 배포 Artifact ID / ZIP SHA-256 | `[증거 대기]` | SHA + ZIP CRC + TAR 내부 해시 |
| 417/941/negative 동일 binary | `[증거 대기]` | 다른 Job 재빌드·SHA 혼합 금지 |
| Protected EI rate custody | `[보호 CI 영수증만; 원본 비공개]` | 동일 Native Job에서 인증→사용→삭제 |
| Original case ZIP immutable | `[P1-0 Artifact #14372278070]` | 최종 Scratch 재생성 시 source lineage 유지 |

**서명 전 체크:** 이 표의 source HEAD, binary SHA, ABI/라이브러리 SHA 중 하나라도 비었거나 정상/음성 Job 사이에 다르면 `SAME_HEAD_BINARY=HOLD`이며 최종 Native PASS 금지.

## B. 입력·Scratch 원본성 (두 사례 각각)

| 필드 | S6-417 | S6-941 | 필요한 자료 |
|---|---|---|---|
| 독립 Scratch 경로 | `[path]` | `[다른 path]` | marker, no symlink, no shared writes |
| 11-layer staged file SHA | `[11/11 PASS/HOLD]` | `[11/11 PASS/HOLD]` | 각 파일 SHA256 + pre/post 영수증 |
| New-only JSON 이름 | `unified_s6_417_newonly.json` | `unified_s6_941_newonly.json` | case 혼합 금지 |
| JSON reference SHA | `ed99493d992c71b30e7a4120646af388894032d262b9af5bf299522629fe24ef` | `2a7d6b191eddf6a92a6bcf74fc818ade8f30836fdd857dc70516f3aa57fa5dde` | final stage에서 동일성 확인 |
| 기존 ion FV 26→0 | `[PASS/HOLD]` | `[PASS/HOLD]` | exact source-deletion block SHA |
| 기존 electron BC/Material 10→0 | `[PASS/HOLD]` | `[PASS/HOLD]` | old BC 8, Functor 2 |
| P4-X 7 duplicate provider edits | `[PASS/HOLD]` | `[PASS/HOLD]` | old C0 section-scoped block SHA |
| `carrier_one` 보존 | `[PASS/HOLD]` | `[PASS/HOLD]` | `1.0`, 단일 생산자 |
| S6 parent plasma original mesh | `[PASS/HOLD]` | `[PASS/HOLD]` | SHA `ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc` |
| Maxwell child `qvt.msh` | `[PASS/HOLD]` | `[PASS/HOLD]` | SHA `a98521af2c106137f9635fe7e2c5ba9b0fd408e17c62eb7c6d3f7c1fff65a03e`, 별도 geometry |
| `electron_moments.txt` | `[PASS/HOLD]` | `[PASS/HOLD]` | 원본 42행, SHA `35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b` |
| neutral transport DB | `[PASS/HOLD]` | `[PASS/HOLD]` | SHA `2fa7988c79f6ea23ebdd50e6d1d7fc5018dc8854a27459511ec95c94ebe7ff3d` |
| EI rate 원본 SHA·보안 Scratch | `[5/5 PASS/HOLD]` | `[5/5 PASS/HOLD]` | 보호된 동일 Job 사용·cleanup 증명; raw 공개 금지 |
| `dont_create_kernels` 우회 없음 | `[PASS/HOLD]` | `[PASS/HOLD]` | source/live input 확인 |
| 입력 P0 authoritative CLI | `[exit/error/log SHA]` | `[exit/error/log SHA]` | 실제 동일 HEAD 검사 |

## C. 실제 Native P2 + P05 Warehouse

| 항목 | S6-417 | S6-941 | 합격 조건 |
|---|---|---|---|
| Physics binary actual SHA | `[64 hex]` | `[64 hex]` | **A와 정확히 동일** |
| Source HEAD / OCI digest | `[값]` | `[값]` | **A와 정확히 동일** |
| `physics-opt --check-input` exit | `[값]` | `[값]` | **둘 다 0** |
| `Syntax OK` | `[true/false]` | `[true/false]` | 둘 다 true |
| 전체 stdout/stderr SHA256 | `[64 hex]` | `[64 hex]` | 실제 로그 원본에 연결 |
| Final Native Run/Job/Artifact | `[IDs]` | `[IDs]` | 분리 경로, 동일 binary |
| `O2p_time/diffusion/drift/source` | `[4/4]` | `[4/4]` | 유일 Factory·변수·name |
| `Om_time/diffusion/drift/source` | `[4/4]` | `[4/4]` | 유일 Factory·변수·name |
| `Op_time/diffusion/drift/source` | `[4/4]` | `[4/4]` | 유일 Factory·변수·name |
| Generated ion FV Kernels | `[12/12]` | `[12/12]` | **실제 Warehouse 12**, legacy 0 |
| Generated ion wall/general+3 dielectric BC | `[12/12]` | `[12/12]` | 실제 Warehouse 12, 양·음 부호/경계 |
| Generated electron FEM BC | `[8/8]` | `[8/8]` | Canonical 단일 소유 |
| `n_e_physical`·`e_wall_number_flux` | `[각 1]` | `[각 1]` | 생산자 중복·누락 없음 |
| `IonWallFluxMaterial` 단일 Factory | `[PASS/HOLD]` | `[PASS/HOLD]` | 유효 등록·동적 호출 |
| `S_O2p/S_Om/S_Op_molar` | `[3/3]` | `[3/3]` | signed EI/H25 채널 일치 |
| P05 unknown/duplicate FV owner | `[0]` | `[0]` | 0개 |
| D8 live Maxwell/RF, neutral, Poisson, Density, Wall, Surface Current | `[PASS/HOLD]` | `[PASS/HOLD]` | 실제 C++/Functor/FaceArg 접근 로그 |
| Protected rate cleanup, original restored | `[PASS/HOLD]` | `[PASS/HOLD]` | 원본 SHA·tmpfs 제거 |

**이전 참고 증거(수용 대체 불가):** 별도 Draft PR [#678](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/678) 의 [Run 44280359966](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44280359966)은 두 case 실제 12+12 P05를 관측했으나 **#665 최종 HEAD 실행이 아니다**. [P5-0 one-build Run 44279232578](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44279232578)은 **이전 HEAD** 실물 바이너리 빌드로만 인정한다.

## D. Native N1–N8 의도적 실패 및 원상 복구

모든 mutant는 정상 case Scratch를 **매번 새로 복제**한다. 하나의 실패가 다음 변이에 영향을 주면 안 된다. 실패 결과를 `CI success`로 대신할 수 없다.

| 슬롯 | 의도한 변이 | 417 actual exit/error/log SHA | 941 actual exit/error/log SHA | 원본 restore SHA | 판정 |
|---|---|---|---|---|---|
| N1 | old `ni_time` 재삽입 | `[ ]` | `[ ]` | `[ ]` | HOLD |
| N2 | old ion diffusion/drift 재삽입 | `[ ]` | `[ ]` | `[ ]` | HOLD |
| N3 | old ion FVBC 재삽입 | `[ ]` | `[ ]` | `[ ]` | HOLD |
| N4 | Physics expected Kernel 이름/타입 충돌 | `[ ]` | `[ ]` | `[ ]` | HOLD |
| N5 | generated BC 중복·변수·sideset 변조 | `[ ]` | `[ ]` | `[ ]` | HOLD |
| N6 | EI/H25 Rate 또는 단일 필수 reaction/source 채널 삭제 | `[ ]` | `[ ]` | `[ ]` | HOLD |
| N7 | 초기 density/transport JSON 누락 | `[ ]` | `[ ]` | `[ ]` | HOLD |
| N8 | 동적 Functor consumer·charge sign·boundary 오연결 | `[ ]` | `[ ]` | `[ ]` | HOLD |

**각 행의 필수 acceptance:** 원본 입력 restore SHA PASS, 의도한 오염 1개 확인, `physics-opt --check-input` **nonzero exit**, 기대한 P0/parser/P05/Functor 실패 단계·정확한 원인 로그, 정상 입력과 **같은 source/binary SHA**. 다른 이유로 실패하면 `FAIL_OR_INCONCLUSIVE`. 단순 정적 모델 거부는 `SOURCE_NEGATIVE`, **Native PASS로 계상하지 않음**.

**N6 보강 필수:** S6-417 및 941의 EI-415/EI-401/EI-417 또는 EI-941/H25 필수 채널 목록 전체가 유지돼야 한다. `hasSpeciesSource()`의 “종별 하나라도 Source 존재” 체크만으로 **부분 반응 채널 누락**이 완전히 거부된다고 주장하지 않는다.

## E. 최종 승격 판정표 (P5-X 단일 Writer만 작성)

| Gate | 현재 작업용 판정 (2026-11-18) | 최종 관측 판정·Evidence ID |
|---|---|---|
| P1 original + P2/P3-X/P4-X final source bytes | PASS_SOURCE | `[ ]` |
| Protected Rate + main/child meshes staged in final runs | SOURCE/SECURE_PASS; Native 연결 HOLD | `[ ]` |
| Wall single Factory and C++ P1 | PASS_PREVIOUS_BUILD | `[ ]` |
| **P5-0 exact FINAL HEAD single binary** | **HOLD** | `[ ]` |
| **417 Native B2 / 941 Native C2** | **HOLD_CURRENT_HEAD** | `[ ]` |
| **Both P05 12 ion Kernels + 12 ion BC + 8 electron BC + unique Functors** | PASS_PROBE_ONLY / HOLD_FINAL | `[ ]` |
| **D8 dynamic callers** | **HOLD** | `[ ]` |
| **N1–N8 two-case actual Native negatives** | **HOLD** | `[ ]` |
| **P5-E4 same HEAD/binary/OCI triplet** | **HOLD** | `[ ]` |
| **Final P5 Native P2** | **HOLD** | `[PASS/HOLD/FAIL]` |
| Scientific P3/P4 equality | **SCIENCE_HOLD / NOT_RUN** | `[별도 결과]` |

### Final decision record

- **Final outcome:** `[ ] PASS_NATIVE_P2` / `[x] HOLD_NATIVE_P2` / `[ ] FAIL_NATIVE_P2`
- **Evidence completeness:** `[ ]` matched final source+binary+417+941+negatives IDs; missing = `[list]`
- **Critical blockers:** `[final exact-HEAD binary, dual-case clean Native/P05, D8, N1–N8 actual negative matrix, full P4-X consumer gate]`
- **Accepted exceptions:** `[none unless documented]` — critical checks cannot be waived by annotation.
- **Scientific decision:** `SCIENCE_HOLD` until separately accepted P3/P4 scientific equivalence.
- **Reviewer / date:** `[P5-X owner / UTC date]`
- **Review commit SHA / Source tree SHA:** `[40 hex]` / `[40 hex]`
- **Final receipt commit / Artifact SHA:** `[40 hex]` / `[64 hex]`
- **Decision evidence URL:** `[permanent link]`

**수용 게이트:** `PASS_NATIVE_P2`는 A–D 전 항목의 동등성·실물 Warehouse·의도적 FAIL 증거가 완결되고 모든 필수 Exit/Artifact/SHA가 맞을 때만. 그 이외에는 HOLD/FAIL로 남긴다. 실제 P3/P4 과학 동등성을 이 양식만으로 PASS 처리하지 않는다.

---

[Source/Artifact 증거 대장](./p5-source-artifact-evidence-ledger.md) · [기계 판독 게이트 인덱스](./p5-evidence-gate-index.json)

## F. W1 바이너리 후보 인계 (P5-X에서 재검증·최종 연결)

**W1 물리적 Artifact byte SHA PASS:** CI [#44293156216](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44293156216), [Artifact #14422701532](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44293156216/artifacts/14422701532), ZIP `ce50a51f2ab565b5dc6aced272adcf12f1075f7593417c603ce05274c8291c18`.

| W1 검증 항목 | 실물 증거 | 최종 P5-X 적용 |
|---|---|---|
| Build HEAD | `05d7ce4eceb81769cb2f0146c51535fc35e74ac1` | PR #665 최신 HEAD와 재대조 |
| Tree | `0385fbf71ef384bbad02a4222f2e799deb02b9a6` | 정확한 tree 동일성 검사 |
| Executable | `cab62a4a9caa4d99a82564f31f915f1a7dc14565607712841123a30276d329bc` | B2/C2/N* 로그에서 같은 SHA 확인 |
| App `.so` | `3274751989604b06e7e7e677435b16c874388a4f7b8735b059eafc605fbb7e51` | 동일 배포 TAR에서 로드 |
| App test `.so` | `86aa0d4ebe18d731e7e052f5ad62594b1a3b48074f848693b0958f728b61ba80` | 동일 배포 TAR에서 로드 |
| Runtime TAR SHA | `705e1f3fa58c4da3c1d76cbca7f2a761045f8f46ee6f54d3391aeaf5ab62033c` | 런타임 파일의 원본 SHA 핀 |
| Build command | `make -C physics_app -j2 app_non_unity_dirs='%/utils'` | 한 차례 빌드 |
| Native `--check-input` | **NOT_RUN** | 417/941 독립 Native 실행 결과 대기 |
| N1–N8 native negatives / D8 | **NOT_RUN** | 실제 exit/log, restore, live callers 대기 |

**W1 후보와 최종 HEAD 구분:** 증거 정리 중 PR #665 HEAD는 `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f`로 전진했고 빌드 HEAD 이후의 diff는 테스트 파일 1개 수정이었다. 이 차이를 명시한 독립 동일성 검증 없이는 W1 ELF를 **최종 HEAD exact build**로 자동 표시하지 않는다. P5-X는 최신 HEAD를 다시 pin한 뒤 동일 바이너리/라이브러리에서 417·941·음성 job이 실행됐음을 실물로 증명한다. 완료 전 `P5_NATIVE_P2=HOLD`, `SCIENCE_HOLD`.

**이 절은 완성된 W8 양식에 최신 W1 실물 값을 전달하는 handoff이며 최종 판정을 대신하지 않는다.**
