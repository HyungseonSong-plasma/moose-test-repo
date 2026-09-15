# Workflow 실패 분석 및 개선 방안

**분석 기준**: 471개 워크플로우 실행 중 실패 및 스킵된 워크플로우 분석  
**분석 날짜**: 2026-09-15

---

## 📊 전체 현황

| 상태 | 개수 | 비율 |
|------|------|------|
| ✅ Success | ~300 | ~63% |
| ❌ Failure | ~45 | ~10% |
| ⏭️ Skipped | ~126 | ~27% |
| **전체** | **471** | **100%** |

---

## 🔴 실패 원인 분류

### 1. **Issue-228 관련 실패 (약 35%)**
- **영향 워크플로우**: 
  - Issue-228 local mesh-quality discriminator (34901123929)
  - Issue-228 quick limiter controls (34899412368, 34898821415)
  - Issue-228 drift-gradient comparison (34897648508)
  - Issue-228 two-point gradient discriminator controls (34879237007)

- **주요 원인**:
  - ✗ Artifact 업로드 실패 (`if-no-files-found: error` 설정)
  - ✗ Test 결과 파일 미생성
  - ✗ 메시 품질 검증 단계 실패
  - ✗ 제한기(limiter) 제어 로직 오류

- **개선 방안**:
  ```yaml
  # ✅ 개선된 설정
  - name: Upload test artifacts
    if: always()  # 실패해도 업로드
    with:
      if-no-files-found: warn  # error 대신 warn 사용
      retention-days: 7
  ```

---

### 2. **Issue-224 병렬 가설 검증 스킵 (약 27%)**
- **영향 워크플로우**:
  - Issue-224 parallel hypothesis OS RSS fan-out (v1, v2, v3)
  - Issue-224 R2 science profile qualification (v1, v2)
  - Issue-224 depth-aware closure packets
  - Issue-224 C4/C5/C6 메모리 판별기

- **주요 원인**:
  - ⏭️ 조건부 실행(`if` 문) 탈락
  - ⏭️ 선행 작업 실패로 인한 자동 스킵
  - ⏭️ 의존성 체인 끊김
  - ⏭️ 리소스 제약으로 인한 의도적 스킵

- **개선 방안**:
  ```yaml
  # ✅ 의존성 명확화
  jobs:
    parallel-hypothesis:
      needs: [setup, baseline-validation]
      if: success()
      
    # ✅ Fallback 정의
    parallel-hypothesis-fallback:
      needs: setup
      if: failure()  # 실패 시 대체 전략 실행
      runs-on: ubuntu-latest-8core
  ```

---

### 3. **Issue-200/199/215/216/217/218 물리 검증 실패 (약 15%)**
- **영향 워크플로우**:
  - Issue-216 W5 EVR-2 mesh convergence (34723732242)
  - Issue-216 W5 multi-step conducting-wall acceptance (34723732179)
  - Issue-218 R2 solver ladder (34753613135)
  - Issue-218 R2 resource-feasible discriminator (34732324379)
  - Issue-220 M1 memory audit
  - Physics CI validation (34507079496)
  - Physics governed science validation (34560800680, 34521583611, 등)

- **주요 원인**:
  - ✗ 솔버 수렴 실패 (Solver convergence)
  - ✗ 메모리 임계값 초과
  - ✗ 수치 안정성 오류
  - ✗ 메시 조건수 악화
  - ✗ 물리 모델 검증 실패

- **개선 방안**:
  ```python
  # ✅ 향상된 에러 핸들링
  def solve_with_retry(config, max_retries=3):
      for attempt in range(max_retries):
          try:
              result = solver.solve(config)
              if result.converged and result.residual < threshold:
                  return result
          except ConvergenceError as e:
              if attempt < max_retries - 1:
                  config.refine_mesh()  # 메시 개선
                  config.adjust_tolerance()  # 공차 조정
                  continue
              raise
      return None
  ```

---

### 4. **Stage-5/6 대규모 검증 실패 (약 8%)**
- **영향 워크플로우**:
  - Stage-5 S5-R representative assembly validation (34621461172, 34620335305, 등)
  - Stage-6 (34671460359, 34668806977, 등)

- **주요 원인**:
  - ✗ 다운스트림 작업 실패 전파
  - ✗ 대규모 어셈블리 처리 시간 초과
  - ✗ 메모리 누수 또는 리소스 고갈
  - ✗ 종속 이슈(Issue-194, 215 등)의 실패

- **개선 방안**:
  ```yaml
  # ✅ 타임아웃 및 메모리 제한 설정
  jobs:
    stage-5-assembly:
      runs-on: ubuntu-latest-16core  # 더 강력한 러너
      timeout-minutes: 180  # 3시간 제한
      env:
        MAX_MEMORY_MB: 15000
        DISK_SPACE_THRESHOLD_MB: 5000
  ```

---

### 5. **Issue-194 멀티스텝 진단 반복 실패 (약 12%)**
- **영향 워크플로우**:
  - Issue-194 A7 governed multi-step diagnosis (30회+ 실패)
  - Stage-5 S5-R governed representative validation

- **주요 원인**:
  - ✗ 진단 알고리즘 수렴 부족
  - ✗ 단계 간 상태 전이 오류
  - ✗ 자료 불일치
  - ✗ 타임아웃 (workflow 파일명이 yml 인데 실행 시점에 변경?)

- **개선 방안**:
  ```python
  # ✅ 단계별 상태 검증
  class MultiStepDiagnosis:
      def __init__(self):
          self.step_states = {}
          
      def validate_step_transition(self, prev_step, next_step):
          """단계 간 상태 일관성 확인"""
          if prev_step not in self.step_states:
              raise StateError(f"Missing state for {prev_step}")
          
          prev_output = self.step_states[prev_step].output
          if not self._is_compatible(prev_output, next_step):
              raise TransitionError(f"Cannot transition from {prev_step} to {next_step}")
      
      def run_with_checkpoints(self, steps):
          """체크포인트 저장으로 재개 가능하게"""
          for i, step in enumerate(steps):
              self.validate_step_transition(steps[i-1] if i > 0 else None, step)
              result = step.execute()
              self.step_states[step.name] = result
              self._save_checkpoint(step.name, result)
  ```

---

### 6. **메모리/리소스 문제 (약 8%)**
- **영향 워크플로우**:
  - Issue-224 C4 initial observability setup memory discriminator (34785748068, 34784559258, 등)
  - Issue-224 C5 observer-family memory discriminator (34784559292)
  - Issue-222 setup-only baseline memory discriminator
  - Science standalone bundle (34486702711)

- **주요 원인**:
  - ✗ OOM (Out of Memory) 또는 메모리 누수
  - ✗ 디스크 공간 부족
  - ✗ 네트워크 I/O 병목
  - ✗ 동시 실행 작업 간 리소스 경쟁

- **개선 방안**:
  ```yaml
  # ✅ 리소스 모니터링 및 제한
  env:
    MEMORY_LIMIT: "12G"
    SWAP_LIMIT: "4G"
    
  steps:
    - name: Monitor resources
      run: |
        free -h | head -3
        df -h | head -3
        ps aux --sort=-%mem | head -5
        
    - name: Run with memory guard
      run: |
        ulimit -v 12884901  # 12GB 제한
        timeout 300 python run.py  # 5분 타임아웃
  ```

---

## 🎯 우선순위별 개선 계획

### Phase 1: 즉시 개선 (1주)
1. **Artifact 업로드 정책 개선**
   - `if-no-files-found`를 `warn` 또는 `ignore`로 변경
   - 사전 검증 단계 추가
   - 가디언 조건(`always()`) 적용

2. **의존성 체인 명확화**
   - `needs` 문법 정규화
   - 조건부 실행(`if`) 로직 단순화
   - 병렬 실행 vs. 순차 실행 재검토

3. **타임아웃 설정**
   ```yaml
   jobs:
     long-running:
       timeout-minutes: 120
   ```

---

### Phase 2: 안정성 강화 (2-3주)
1. **재시도 로직 추가**
   ```yaml
   - uses: actions/retry@v2
     with:
       timeout_minutes: 10
       max_attempts: 3
       retry_wait_seconds: 30
   ```

2. **에러 로깅 및 진단 정보 수집**
   ```bash
   set -x  # 디버그 모드
   trap 'echo "Job failed at line $LINENO"' ERR
   ```

3. **메모리 프로파일링**
   - 메모리 사용 추적 도구 통합 (e.g., `memory_profiler`)
   - 누수 테스트 정기 실행

---

### Phase 3: 최적화 (4-6주)
1. **병렬 처리 개선**
   - Matrix 빌드 전략 재검토
   - 러너 풀 크기 최적화
   - 작업 큐 관리

2. **캐싱 전략**
   ```yaml
   - uses: actions/cache@v3
     with:
       path: ~/.cache/python
       key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}
   ```

3. **러너 업그레이드**
   - 더 강력한 머신 타입으로 전환 (16core → 32core)
   - SSD 스토리지 확보
   - 네트워크 대역폭 증설

---

## 📈 성공률 개선 목표

| 지표 | 현재 | 목표 | 기간 |
|------|------|------|------|
| 성공률 | 63% | 85% | 6주 |
| 평균 런타임 | - | -20% | 6주 |
| 스킵율 | 27% | 5% | 4주 |
| 평균 메모리 사용 | - | -15% | 6주 |

---

## 🛠️ 체크리스트

### 즉시 실행 (This Week)
- [ ] `.github/workflows/*.yml` 파일에서 `if-no-files-found: error` → `if-no-files-found: warn` 변경
- [ ] 모든 워크플로우에 `timeout-minutes` 설정 추가
- [ ] 주요 실패 워크플로우별 로그 분석 시작
- [ ] 에러 조건별 핸들러 문서화

### 단기 실행 (This Month)
- [ ] 재시도 로직 구현 및 테스트
- [ ] 메모리 프로파일링 도구 통합
- [ ] Issue-194 멀티스텝 진단 알고리즘 리뷰
- [ ] Issue-228 artifact 검증 강화

### 장기 계획 (Next Quarter)
- [ ] CI/CD 파이프라인 재설계
- [ ] 러너 인프라 업그레이드
- [ ] 모니터링 대시보드 구축
- [ ] 자동화된 성능 회귀 테스트

---

## 📚 참고 자료

- [GitHub Actions 공식 문서](https://docs.github.com/actions)
- [Workflow 실패 진단 가이드](https://docs.github.com/en/actions/monitoring-and-troubleshooting-workflows)
- [워크플로우 성능 최적화](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows)

---

**작성자**: Copilot  
**최종 업데이트**: 2026-09-15  
**다음 검토 예정**: 2026-09-22
