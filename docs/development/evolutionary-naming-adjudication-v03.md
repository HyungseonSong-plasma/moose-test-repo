# Evolutionary Naming Audit — GPT recommendation adjudication v0.3

**Status:** experimental read-only adjudication on top of v0.1 option model and
v0.2 historical Git evidence (Issue #769 / Draft PR #770).

## Why an additional gate?

`REVIEWABLE` from the v0.1 `NamingOption` contract says the **proposal is
sufficiently specified**. It does **not** establish that a proposed name is
better, that extracted responsibilities are coherent, or that any edit is safe.
The GPT recommender must be constrained by competing candidate evidence, and
the submitted evidence must be independently source-anchored.

## Stable process

```text
exact Git history and responsibility hypotheses
  -> current name-fit / coherence assessment (interpretation, not proof)
  -> KEEP, RENAME, EXTRACT_KEEP, EXTRACT_RENAME, HOLD alternatives
  -> build_naming_recommendation_brief (KEEP required)
  -> GPT comparative argument: preferred, why-not-KEEP, rebuttals,
     rejected alternatives and concrete evidence refs, unresolved questions
  -> independent Git path:line@blob and revision-ancestry verifier
  -> compare alternatives and current-vs-historical witness freshness
  -> KEEP / RECOMMEND_FOR_VERIFICATION / HOLD (never authorized mutation)
  -> *separate* independent semantic reviewer and before/after executor gate
```

## Adjudication contract

A recommended change needs all of:

- exactly one KEEP option and every alternative assessed;
- complete source references bound to real immutable Git trees, including
  historical witnesses on an **ancestor** commit and current responsibility;
- concrete counterexample to keeping the present name for RENAME (and for
  EXTRACT_RENAME), with current `NAME_MISMATCH` evidence;
- source-grounded positive responsibilities and excluded negative boundary;
- extraction implementation owners, residual responsibilities, and proven
  proposal seam if extraction is suggested;
- no unresolved identity/unknown source evidence or model-reported ambiguity.

Name quality is **not** a single numerical score. A valid generic name is
preferred over a more detailed name, even if the latter appears more explicit.
An existing semantic owner (`diagnostics/providers`) should not be duplicated.
`EXTRACT_KEEP` is allowed: changing structure does not require changing names.

## Negative controls

- Changed worktree bytes must not replace immutable Git source evidence.
- Incorrect blob, nonexistent line or a future/unrelated revision -> HOLD.
- No old Git objects in shallow clone -> HOLD, never re-label current bytes.
- Renaming a still-valid general name -> HOLD/REJECTED; do not auto-rename.
- No explicit rebuttal of KEEP, missed competitor, fabricated citation,
  contradictory or unresolved assertions -> HOLD.
- Even a validly anchored and well-argued GPT candidate yields only
  `RECOMMEND_FOR_VERIFICATION`. Source line presence does not prove its
  text description, independent semantic review or behavioral compatibility.

## Real repository control

The existing common `diagnostics/collector.py` owns a generic collector
protocol and scan entrypoint, with language-specific implementations already
separated under `diagnostics/providers/{python_ast,cpp,moose_input}.py`.
On the exact PR HEAD the integration test reads the current Git Blob and
checks source anchors, but the name-fit/coherence label is a **manual
hypothesis**, not independent natural-language validation. Its selected
option remains KEEP. Prior-history objects are verified in isolated two-commit
fixtures, not assumed accessible in the shallow production checkout.

## Remaining gates

1. Independent semantic owner and negative-boundary validation, preferably
   from held-out human reviewers or separate evidence paths.
2. External/dynamic consumer closure, public API compatibility, namespace
   ambiguity and broad language support (Python/C++/MOOSE).
3. Isolated candidate edits, revision-bound checks, behavior equivalence,
   rollback and post-change HEAD verification.

No production rename, extraction, PR merge, or mutation authorization in v0.3.
