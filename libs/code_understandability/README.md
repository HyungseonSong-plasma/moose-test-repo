# Code Understandability Metrics

Canonical engine for **source-grounded code understandability indicators**.
The engine is not restricted to how humans subjectively rate code and does not
assert that any individual measurement proves code is easy to understand.

## Measurement contract

- `from_python_ast()` transports existing Diagnostics LOC, branch and maximum
  branch-nesting measurements into typed, source-bound structural inputs.
- `derive_indicators()` computes `branch_density` and
  `candidate_call_density` only where real source facts are available.
- `evaluate_understandability(UnderstandabilityInput(...))` calculates the
  indicators, preserves source revision and blob identity, and carries
  evidence/provenance and explicit unknowns.
- `compare_understandability(before, after)` reports numerically comparable
  structural and indicator differences without claiming a quality improvement.
- `HumanObservation` and `ObservedHumanResponse` represent optional
  human judgments. Responses are grouped by question and criterion; a rate
  requires at least two independent raters for that same question.

No human assessment is required to calculate source-backed code indicators,
and the absence of a human observation is **not** a general metric failure.
There is currently **no calibrated overall understandability score, universal
weighted metric, semantic cohesion inference, or automatic verdict**.

## Canonical API

```python
from libs.code_understandability import (
    UnderstandabilityInput, evaluate_understandability, from_python_ast,
)

measurement = from_python_ast({"loc": 20, "branches": 4})
sample = UnderstandabilityInput(
    "node:example", "a" * 40, "b" * 40, structural_metrics=measurement,
)
assessment = evaluate_understandability(sample)
assert assessment.indicators[0].value == 0.2
assert assessment.predicted_score is None
```

## Layer boundaries

Diagnostics collects source and graph evidence; this engine computes
indicators; `analysis/understandability_adapter.py` transports data and
`analysis/understandability_interpretation.py` evaluates contextual meaning;
Refactor Planning compares alternatives and Verification checks preservation.

The historical `libs.hu` and `analysis.hu_*` imports remain as
compatibility facades. The persisted `hu_density_v1` method identifier and
some legacy error identifiers stay unchanged to preserve data comparisons.
Migration does not alter what those methods measured or claim new metrics.
