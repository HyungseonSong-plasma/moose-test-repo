# Evolutionary Naming Audit — Recommendation & Extraction Contract v0.1

**Status:** experimental read-only planning contract; no automatic rename or extraction enabled by this patch.  
**Scope:** folder / file / class / function.  
**Owner:** `physics_harness/code/refactor/naming.py` (specific naming policy) → canonical `refactor/planning.py` (strategy-neutral validation) → independent candidate verification → governed repository-mutation executor.

## Objective

Prefer a **stable responsibility name**, not the most descriptive name of today’s implementation. A name that already covers the observed core responsibility should remain (`KEEP`) despite prettier/more specific alternatives. Future features cannot be invented to justify changing it. Distinguish whether the change should be *naming only* or *responsibility extraction + naming*; do not conflate the two.

## Decision stages

1. **Evidence and continuity:** pin exact repo revision, tracked file/blob witness, logical identity, observed responsibilities, exclusions, evolution facts, consumption contracts, co-/change-history, and uncertainty. File path identity is not sufficient for a split/merge of logical owners. Data is source-backed; interpretation is not asserted to be fact merely because it has an evidence ID.
2. **Assess original:** label whether it is `VALID`, `NARROW`, `MISLEADING`, or `UNKNOWN` and whether its responsibilities are `COHERENT`, `MIXED`, or `UNKNOWN`. `VALID` defaults to `KEEP`—even if a different name sounds more professional.
3. **Generate options:** `KEEP`, `RENAME`, `EXTRACT_KEEP`, `EXTRACT_RENAME`, `HOLD`; include `EXTRACT_KEEP` because a structural improvement does **not** imply a naming defect. Do **not** treat an extraction destination path (`libs/`, `providers/`) as canonical until its semantic owner has been checked. Do not create layers solely to justify generalization.
4. **GPT recommendation constraints:** for each changed name supply:
   - coverage rationale — which *existing, observed* responsibilities it includes;
   - boundary rationale — what it must **not** imply;
   - context rationale — why folder/module/class/function lexical context makes short name sufficient;
   - cited mismatch, evolution, boundary, existing namespace, and extraction-seam evidence;
   - reject over-specific / over-broad / peer-colliding alternatives with explicit reasons.
   No aggregate numerical quality score, forced winner, or guessed future implementations. When multiple candidates remain equivalent, return `HOLD/REVIEW`.
5. **Responsibility allocation:** for `EXTRACT_*`, record each extracted owner, its chosen name, destination, seam and previously observed responsibility IDs. Record what remains in the original owner. The union of post-change allocated responsibilities must cover *exactly* the original declared responsibilities. An orchestrator may retain accountability for a delegated implementation; allocations are not forced disjoint. Check name suitability **again against the residual responsibility after extraction**, not before.
6. **Plan review:** reject fabricated responsibilities, missing seams, name collisions, name changes where the current name remains valid, wrong logical identity, missing explanations, and unbounded edits. `REVIEWABLE` means structurally complete for further review, **not safe to mutate**. Map to existing `PlanningAlternative(action=CHANGE)` and existing validation path; no parallel mutation implementation.
7. **Independent execution gates:** sandbox candidate tree/commit → verify exact before/after revisions, reference and consumer closure, public APIs / dynamic import paths / files / workflows / persisted identifiers, behavior before and after, extraction initialization and dependencies, semantic equivalence within explicitly recorded scope, regression tests, idempotence, rollback. GPT-authored check receipts cannot self-authorize. A textual `PASS` without an independent verifier and binding to candidate SHA is not an authorization. After-head validation is mandatory. Unresolved external compatibility → `HOLD`.
8. **Governed mutation:** only after the independent executor has its own checks and policy/approval authority may `RENAME` or `EXTRACT_*` apply automatically. This module always returns `mutation_approved=False`.

## Concrete evidence from current repository

At `main@4f873e71f8503943c9fce2dd30fcc96c28d6f631`, the requested separation is **already present**, not an improvement to repeat:

- `physics_harness/code/diagnostics/collector.py:125–140` (`blob 3f169372d13a8d89ed9565eedfbcd3f18cb3c435`) defines generic `SourceProvider`, `Collector` contracts and `run_scan`.
- `physics_harness/code/diagnostics/providers/python_ast.py:52–59` (`blob 8a4de081c3b3f722ca3d651e84b6e01dc14c7978`) owns `PythonAstCollector`.
- `physics_harness/code/diagnostics/providers/cpp.py:124–131` (`blob b4e8b061ef3ec2bb9f78e7b3b20734eb9c04710c`) owns `CppSourceCollector`.
- `physics_harness/code/diagnostics/providers/moose_input.py:43–50` (`blob ac6201b96a15624d0dac8ae7e32f888582a32f90`) owns `MooseInputCollector`.

These **structural** facts support a KEEP-first candidate for the existing generic `collector` name and delegating provider owners. They do **not** prove complete historical evolution, all external consumers, runtime semantic compatibility or correctness of the entire module. There is no justification for manufacturing a new `libs/` layer to reproduce this already delegated design.

## P0 adversarial controls

- Broad stable name: `KEEP` baseline; gratuitous rename `REJECTED`.
- Name too narrow, responsibilities coherent: rename becomes `REVIEWABLE`, not executable.
- Mixed responsibilities: rename-only rejected; extraction + rename requires a verified seam and preserving all prior responsibilities.
- Extraction with no name change is permitted when supported; no inventing responsibility or silently dropping one.
- Missing contextual negative boundary / evolution source / identity / post-extraction name fit → `HOLD`.
- New destination vs existing owner distinguishes **create** and **modify**; no root `libs/` assumption.
- Every candidate requires independent before-after compatibility / consumer / init order / regression checks; no self-certified PASS.

## Deferred

Automatic discovery of historical logical owners (moves/splits/merges), GPT semantic suitability calibration, true consumer closure, AST edits, external compatibility preservation, and the independent mutation executor. None is falsely claimed by this read-only contract.
