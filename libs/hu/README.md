# HU library (v0.1)

Independent Human Understandability (HU) measurement primitives.

## Contract

- `from_python_ast(attributes, evidence_ids=...)` converts **existing** AST
  collector measurements (`loc`, `branches`, `max_branch_nesting`) into
  descriptive, source-bound structural covariates. Parsing/AST collection is
  not duplicated in this library.
- `evaluate_hu(HUInput(...))` keeps structural features separate from
  actual evaluator judgments. It never invents a predictive HU score.
- `HUObservation` identifies evaluator, question, criterion, baseline revision,
  exact source blob, and one binary observation. Distinct questions/criteria
  are never pooled. Duplicate evaluator/question pairs fail closed.
- `ObservedHU.positive_rate` is emitted only for **two or more independent
  evaluators** of the same question and criterion. One evaluation is preserved
  as 0/1, not promoted to a population-quality percentage.
- `evaluation.compare_hu(before, after)` reports comparable structural deltas. A
  reduction in branches or LOC is **not** a proven improvement in HU.
- Semantic cohesion, name/body alignment, behavioral correctness, and
  understandability gain require additional study/evidence. They are not
  synthesized from control-flow counts.

## Independence

The before/after comparison is kept alongside evaluation in `evaluation.py`;
there is no separate comparison module. The public `libs.hu.compare_hu` API is
preserved.

This library imports only Python standard-library modules, and does not import
`physics_harness`, modify code, or select any refactoring strategy. Source
provenance is passed in as identity data; the caller authenticates the source.

Version 0.1 does not implement a calibrated, predicted HU probability, a
weighted aggregate score, or an automatic pass/fail gate.
