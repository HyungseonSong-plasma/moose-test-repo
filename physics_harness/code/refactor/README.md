# Refactor: evidence-based planning contracts (v0.1)

Refactor Planning organizes **existing** source facts, analyses and constraints
into reviewable change alternatives. It does not select a universal "best"
transformation, edit the repository, or authorize a change.

## Ownership

| Package | Responsibility |
| --- | --- |
| `code/diagnostics/` | Exact-source graph, evidence, receipt and collection completeness |
| `libs/code_understandability/` | Numeric code-understandability features from existing source facts and observations, no interpretation or refactor decision |
| `code/analysis/result.py` | Generic revision-bound analysis records and measurements |
| `code/analysis/understandability_adapter.py` | Diagnostics↔metric engine data mapping and Evidence transport only |
| `code/analysis/understandability_interpretation.py` | Interpret calculated code-understandability indicators, caveats and trade-offs for Planning |
| `code/refactor/planning.py` | Source-bound context and constraint validation |
| `code/refactor/alternatives.py` | Apply the same checks to alternative proposals; no ranking |
| `code/verification/` | Independent source/contract checks, post-change obligations |

The **scope of a structural change** is independent of its **objective**:
conceptual/data architecture, folder/module organization, and implementation
internals can all use the same planning contracts. Code-understandability metrics apply most directly to
implementation internals, but no folder or architecture policy is hard-coded.

## Data flow

```
run_scan -> DiagnosticResult
  -> assess_code_understandability(...) -> libs.code_understandability.UnderstandabilityAssessment
  -> summarize_understandability(...) -> AnalysisRecord
  -> interpret_understandability_indicators(...) -> AnalysisRecord
  -> build_planning_context(..., assessments=(record, interpretation))
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
from physics_harness.code.analysis.understandability_adapter import assess_code_understandability, summarize_understandability
from physics_harness.code.analysis.understandability_interpretation import interpret_understandability_indicators
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
hu = assess_code_understandability(scan, target.id)
record = summarize_understandability(hu)
interpretation = interpret_understandability_indicators(hu)
context = build_planning_context(
    scan, target.id,
    assessments=(record, interpretation),
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

- Structural AST counts are **not** code-understandability scores. Actual observed human outcomes
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

`test_understandability_run_scan_integration.py` and `test_code_understandability.py` test the real collector → code-understandability metrics → Analysis →
Planning flow using the existing `git_factory` fixture. engine-only changes in
`libs/code_understandability/**` do not currently trigger the existing path-filtered Harness Code
workflow by themselves; test ownership and scheduling need a separate scoped
policy decision rather than broadening CI implicitly.

## Evolutionary Naming Audit: candidate policy (v0.1)

`refactor/naming.py` handles the *naming-specific* question without changing
the generic `PlanningAlternative` contract or authorizing a repository edit.
Its evidence is a declared, source/commit-anchored hypothesis; this policy
can validate **completeness and contradictions**, not independently establish
that GPT's interpretation is true.

- `KEEP` (default): current short/general name covers the actual core duty.
- `RENAME`: observed name-scope mismatch and coherent duty; no extraction.
- `EXTRACT_KEEP`: independently warranted responsibility delegation, with the
  original name still appropriate **after** extraction.
- `EXTRACT_RENAME`: proven extraction seam with an appropriate name for both
  the residual owner and extracted implementation owner.
- `HOLD`: missing identity, meaning, ownership, boundary, destination or checks.

Required option evidence: **observed responsibility, evolution, name mismatch
(when renaming), negative boundary, repository context**, and extraction seam
(when extracting). GPT must explain positive coverage, excluded duties and
contextual interpretation; it cannot claim a future implementation as evidence.
Both name changes and structural extraction must preserve the declared set of
responsibilities; delegation may leave the top-level owner accountable for the
service. Avoid a hardcoded `libs/` destination: first reuse an actual current
semantic owner (e.g., existing providers).

`review_naming_option` rejects wrong-scope proposals and reports independent
checks; `to_planning_alternative` maps reviewable candidates back to the
existing strategy-neutral planning and validation path. **REVIEWABLE is not a
mutation authorization.** An independent runner must bind source evidence to
exact Git blobs, verify before/after candidate SHA, dynamic/external consumers,
public contracts, behavior, idempotence, and rollback before automatic mutation.

Concrete baseline at `main@4f873e71f8503943c9fce2dd30fcc96c28d6f631`:
`diagnostics/collector.py` already owns `Collector`/`SourceProvider` contracts
and `run_scan` (lines 125–140); Python, C++ and MOOSE Input implementations are
already isolated in `diagnostics/providers/`. This existing separation is a
reason to consider **KEEP** rather than invent another `libs/` hierarchy. It is
not evidence of whole-repository semantic equivalence.

See `docs/development/evolutionary-naming-audit-contract.md` for the detailed
recommendation, extraction and verification obligations.


## Historical responsibility evidence (v0.2, read-only)

The naming-specific `refactor/evolution.py` analyzes **exact Git blobs** for
Python declarations, module dependencies and delegation between a declared
local protocol and an imported class implementing the same *method names*.
It deliberately observes syntax, not runtime behavior or abstract semantics.
The pre-existing Git source owner now exposes
`GitSourceProvider.read_at_revision(exact_40_hex_sha, literal_path)`:
local commit tree -> tracked regular blob -> validated byte content. Historical
commits that are unavailable in a shallow clone fail closed; no implicit
fetch, worktree fallback or synthetic history evidence.

`audit_git_history(...)` checks that the before commit is an ancestor of the
after commit, resolves exact historical blobs for a named owner and explicit
provider inventory, compares top-level declarations/imports, and distinguishes
already-isolated delegation from inline implementation candidates. New
imports do **not** prove a new responsibility, and unchanged symbol names do
**not** prove logical identity or behavioral compatibility. Results include
`FUNCTION_BODIES_NOT_SEMANTICALLY_COMPARED` when byte content changes.

- `KEEP_CONSIDERATION`: stable declarations with newly observed external owner
  seams; GPT must still establish current responsibility and name validity.
- `EXTRACTION_REVIEW`: an inline class with methods exists; independent
  cohesion, separation cost, and contract checks remain required.
- `HOLD`: identity or evidence missing, or no change justified.

These are *evidence dispositions*, not `KEEP`/`RENAME` decisions. They never
trigger a change and never grant mutation authority. To propose a change,
pass independent responsibility/name-fit/boundary evidence through
`NamingCase` and `review_naming_option`; then canonical Planning/Verification.

**Real historical negative control:** `diagnostics/collector.py` gained Python,
C++ and MOOSE Input provider imports while retaining `Collector`,
`SourceProvider` and `run_scan` declarations. The implementations are already
in `diagnostics/providers/`. Evidence: `experiments/evolutionary_naming_audit/`
and `docs/development/evolutionary-naming-audit-history-v02.md`. Historic
GitHub objects were inspected when the fixture was recorded; shallow CI
only replays its own self-contained two-commit Git test and validates the
current HEAD source. The frozen older-commit summary alone is not a CI
semantic-evidence proof.

## Evolutionary naming — v0.3 comparative GPT recommendation gate

**New, read-only stage; no automatic executor or mutation permission.** After
source-backed historical structure evidence and reviewable `NamingOption`s exist:

1. Use `build_naming_recommendation_brief(case, options)` to pass a bounded,
   revision-specific evidence/option inventory to GPT. Include **exactly one
   KEEP baseline**. GPT must compare every alternative rather than generate an
   arbitrary "best-sounding" name. Keep existing stable responsibilities by
   default, and do not guess future functionality.
2. Ask GPT for a `NamingRecommendation`: selected option, explicit reason not to
   KEEP (if change), current mismatch evidence IDs, a reason for rejecting
   **every** alternative, and unresolved questions. A recommendation is only a
   proposed argument; it does not authenticate cited facts.
3. Run `adjudicate_naming_recommendation(case, options, suggestion, provider)`.
   This calls independent `verification/naming_provenance.py`, reading exact Git
   object bytes for **every** path:line@blob claim, including ancestral history.
   Missing commits, stale observations or contradictions cause HOLD.
4. Only `KEEP`, `RECOMMEND_FOR_VERIFICATION`, or `HOLD` may emerge. A change
   recommendation must have a concrete historical witness, a **current**
   responsibility and mismatch witness, KEEP rebuttal, complete competitor
   comparisons, and a structurally reviewable NamingOption. It still requires
   semantic role/name review, all consumer/contract checks, candidate staging,
   behavioral regression, idempotence and post-HEAD verification.

**Important limitations:** an exact source line is not a machine-verifiable
proof of the natural-language `NamingEvidence.statement`, responsibility
coherence, name fit, change need or safety. The same GPT may have produced
both evidence interpretations and the choice. Consequently, even
`RECOMMEND_FOR_VERIFICATION` always has `mutation_approved=False`. Verify
semantic correctness independently, ideally with held-out reviewers and real
consumers, *before* building an automatic executor. A clone without old Git
objects yields HOLD rather than silently comparing to current worktree bytes.

## Evolutionary Naming Audit v0.4 — independent boundary and candidate-Git checks

`code/verification/naming_boundary.py` is an **independent, exact-Git-source
structural gate** for naming/extraction recommendations. An assessor must map
observed responsibility IDs to precise declarations, e.g.
`path.py::class:Collector`, `path.py::function:run_scan`, or
`path.py::method:Collector.collect`, grounded by the current responsibility's
*declaration-line* `path:line@blob` witness. It checks folder/file/class/function
scope, stale or invented symbols, split ownership, actual existing destination
vs claimed new path, and source completeness budgets. It reuses the canonical
GitSourceProvider and independent source-anchor verifier.

`code/verification/naming_candidate.py` checks a **distinct descendant Git
commit** resulting from an *isolated proposed* rename/extract change. A complete
`CandidatePlacement` map must account for the before symbols: original vs
extracted owner, expected after symbol/path, declaration signature consistency,
missing or duplicated symbols, wrong destination, and original name retention
for `EXTRACT_KEEP`. The verifier **never creates commits, executes changes,
validates external imports/runtime behavior, or approves mutation**.

`STRUCTURE_WITNESSED` and `STRUCTURAL_DELTA_VERIFIED` are syntactic structural
claims, **not semantic truth or behavioral compatibility**. They are not equivalent
to the earlier `REVIEWABLE` decision, nor enough for automatic changes. Even with
both receipts, the executor must obtain an **independent semantic name/ownership
review**, public/dynamic consumer closure, before/after behavioral regressions,
exact candidate and post-integration HEAD tests, provenance receipt and rollback
boundary. Unverified mandatory properties produce `HOLD` rather than implicitly
passing. No hardcoded domain vocabulary, destination `libs/` path, or universal
naming score is introduced.
