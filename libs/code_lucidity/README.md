# Code Lucidity Metrics

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
from libs.code_lucidity import (
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
indicators; `analysis/lucidity_adapter.py` transports data and
`analysis/lucidity_interpretation.py` evaluates contextual meaning;
Refactor Planning compares alternatives and Verification checks preservation.

The retired `libs.hu` and `analysis.hu_*` import paths are not supported.
Use `libs.code_lucidity` and the canonical Analysis entry points.
The persisted `hu_density_v1` measurement-method identifier remains unchanged
only as **historical data identity** for comparing earlier measurements. Its
spelling does not imply human evaluation is required.

## Exploratory Definition CU (Issue #767, Draft)

`definition_metrics.py` and `definition_discrimination.py` provide source-linked,
lexical Definition Explanation Burden (DEB), Minimum Required Context (MRC)
and contrastive definition controls. They are **uncalibrated research proxies**,
not human comprehension evidence, naming acceptance criteria, or authority to
rename, compress, remove, or refactor production code. Frozen historical
measurements retain their original exact-source provenance.

Old imports under `libs.code_understandability.definition_*` remain
identity-preserving compatibility re-exports; new code should use this package.
