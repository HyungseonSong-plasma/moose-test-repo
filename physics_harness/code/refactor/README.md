# Refactor: evidence-based planning contracts (v0.1)

Refactor Planning organizes **existing** source facts, analyses and constraints
into reviewable change alternatives. It does not select a universal "best"
transformation, edit the repository, or authorize a change.

## Ownership

| Package | Responsibility |
| --- | --- |
| `code/diagnostics/` | Exact-source graph, evidence, receipt and collection completeness |
| `libs/hu/` | HU structural measurements, human observations, and descriptive comparison |
| `code/analysis/result.py` | Generic revision-bound analysis records and measurements |
| `code/analysis/hu_adapter.py` | Diagnostics → HU library → generic AnalysisRecord |
| `code/refactor/planning.py` | Source-bound context and constraint validation |
| `code/refactor/alternatives.py` | Apply the same checks to alternative proposals; no ranking |
| `code/verification/` | Independent source/contract checks, post-change obligations |

The **scope of a structural change** is independent of its **objective**:
conceptual/data architecture, folder/module organization, and implementation
internals can all use the same planning contracts. HU applies most directly to
implementation internals, but no folder or architecture policy is hard-coded.

## Data flow

```
run_scan -> DiagnosticResult
  -> assess_code_hu(...) -> libs.hu.HUAssessment
  -> summarize_hu(...) -> AnalysisRecord
  -> build_planning_context(..., assessments=(record,))
  -> review_alternatives(...)
  -> post-change Verification [separate]
```

The `run_scan()` request currently selects files/collectors; `ScanRequest.roots`
is not an implemented symbol filter. Select the target Graph node **after** scan.
`python_ast` emits candidate imports/calls, not resolved runtime calls.

Example in a real repository checkout:

```python
from pathlib import Path
import subprocess

from physics_harness.code.diagnostics import GitSourceProvider, ScanRequest, run_scan
from physics_harness.code.analysis.hu_adapter import assess_code_hu, summarize_hu
from physics_harness.code.refactor import (
    HardConstraint, PlanningAlternative, build_planning_context, review_alternatives,
)

root = Path.cwd()
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
path = "physics_harness/code/verification/dependencies.py"
scan = run_scan(
    ScanRequest(
        repository="HyungseonSong-plasma/moose-test-repo",
        revision=head,
        includes=(path,), collectors=("python_ast",),
    ),
    GitSourceProvider(root),
)
target = next(n for n in scan.graph.nodes
              if n.kind == "python_function" and n.name == "verify_dependencies")
hu = assess_code_hu(scan, target.id)
record = summarize_hu(hu)
context = build_planning_context(
    scan, target.id,
    assessments=(record,),
    objectives=("Clarify import processing while preserving behavior",),
    hard_constraints=(
        HardConstraint("first_match", "Preserve first-matching-rule priority"),
    ),
)

options = (
    PlanningAlternative("baseline", "KEEP", "Preserve current source"),
    PlanningAlternative(
        "split_reference_reader", "CHANGE",
        "Explore whether separating AST extraction makes the function clearer",
        affected_paths=(path,), evidence_ids=context.target_evidence_ids[:1],
        expected_benefits=("Potentially clearer extraction/decision boundary",),
        risks=("Might change rule precedence or output ordering",),
    ),
)
review = review_alternatives(context, options)
for verdict in review.results:
    print(verdict.alternative_id, verdict.disposition,
          verdict.unknowns, verdict.required_checks)
```

## Semantics

- Structural AST counts are **not** HU scores. Actual observed human outcomes
  remain separated by question/criterion and provenance; no automatic score
  weighting, prediction, or quality ranking.
- Every proposed change may be compared with a `KEEP` baseline.
- Proposals name existing `affected_paths` and optional `created_paths` /
  `removed_paths`. Proposed new destinations are *not* required to appear in a
  pre-change scan, but require baseline absence and after-HEAD verification.
  Removal requires consumer/reference checks. Missing existing-source scope
  yields `HOLD` rather than pretending consumer closure.
- `ConstraintCheck` is an independently supplied result with exact revision,
  alternative ID and evidence refs. A string `check_ref` cannot authenticate
  verification; consumers must validate the referenced test/review receipt.
- `BLOCKED` means a contradiction, invalid evidence, or failed hard constraint;
  `HOLD` means required evidence or checks are missing; `ADMISSIBLE` means
  sufficient structural support to **consider** the proposal. None of these
  states grants mutation approval. Runtime/semantic compatibility must be
  verified separately after implementation.

## Tests and CI

New self-tests reside under `physics_harness/code/tests/`.

```bash
python -m pytest -q physics_harness/code/tests
```

`test_hu_run_scan_integration.py` tests the real collector → HU → Analysis →
Planning flow using the existing `git_factory` fixture. HU-only changes in
`libs/hu/**` do not currently trigger the existing path-filtered Harness Code
workflow by themselves; test ownership and scheduling need a separate scoped
policy decision rather than broadening CI implicitly.
