# Issue53 Efficiency extraction transcription drift incident — 2026-09-01

**Status:** repaired / recorded  
**Affected work:** #53 `qpx-stats-builder-decomposition`  
**Affected file:** `qpx_harness/analysis/stats_builder.py`

## Incident

The intended D1 change was limited to removing the monolithic Efficiency mapping implementation from `stats_builder.py` and re-exporting `build_efficiency_stats` from `analysis/metrics/efficiency.py`.

During the complete-file replacement payload, one unrelated closing parenthesis in `_variable_residual_samples()` was omitted:

```python
out.append(
    ResidualSample(
        ...
    )
# missing: )
return out
```

This introduced a syntax/structural defect outside the intended Efficiency extraction scope.

## Detection

The defect was detected immediately by post-write commit-diff verification before any user-local D1 validation was requested. The commit diff showed an unexpected deletion in `_variable_residual_samples()` in addition to the intended Efficiency extraction.

## Repository history

```text
959487a5348488ae7bb3ccd3196e68d1677048ec
  refactor(issue53): extract EfficiencyStats owner
  -> intended Efficiency extraction plus accidental parenthesis deletion

64d1ab4c074262662b56b9b42f81e59e7db38388
  repair(issue53): restore residual append closure
  -> restored the missing parenthesis; also restored final newline
```

## Impact

- no physics or numerical semantics were intentionally changed;
- the accidental state was not accepted by user-local validation;
- the defect would have broken Python parsing/execution on the affected module;
- post-write verification contained the incident before D1 validation or D2 work;
- D1 remains pending local validation after repair.

## Root cause

**Full-file replacement transcription drift during a narrow structural extraction.**

This is the same semantic failure class as the earlier #50 Issue46 Stats migration drift: a narrow intended change was implemented through a manually reconstructed complete replacement payload and an unrelated unchanged region drifted.

## Learning classification

Primary MET-20 status: `KNOWN_AND_GATE_BYPASSED`.

Pre-existing owners already covered preservation of unchanged scope and complete replacement-byte safety:

```text
docs/protocols/coding.md CODE-10
docs/protocols/repository_mutation.md RM-01 / RM-03 / RM-06B
docs/protocols/rule_working_set.md RWS-05A
```

Applicable pack: `IMPLEMENT / MUTATE`  
Rule/pack active: `yes`  
Machine gate before incident: `no`  
Detection stage: `post-write commit-diff verification`

## MET-22 Enforcement Promotion Review

EPR required: `yes`.

Reason: this is the second classified known recurrence of the same semantic full-file-replacement transcription-drift class after canonical coverage existed.

Primary EPR decision: `PROMOTE_TO_MACHINE_GATE`.

Required implementation direction for subsequent destructive #53 cuts:

```text
before accepting a structural extraction cut:
1. mechanically parse the resulting Python target;
2. mechanically characterize the intended removed/added symbol set;
3. reject unexpected changes outside the declared extraction domain;
4. keep destructive cuts one domain at a time with immediate local validation.
```

The existing post-write read-back remains containment, not prevention. Prevention maturity remains `DOCUMENTED` until an executable applicable-path guard with discriminating negative/mutation evidence is installed and demonstrated.

## Immediate containment

D1 was repaired before user-local validation. D2 Convergence removal is blocked until the repaired D1 local gate passes.
