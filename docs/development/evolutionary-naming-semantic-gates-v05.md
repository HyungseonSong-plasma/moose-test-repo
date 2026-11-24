# Evolutionary Naming Audit — Candidate Semantic Challenge v0.5

**Status:** exact-source read-only falsification and independent-review handoff. **No automatic rename/extraction or mutation approval.** This complements the v0.1–v0.4 naming, Git evolution, recommendation, ownership and candidate placement contracts in #769 / Draft PR #770.

## Why structural PASS was insufficient

Before: `def python_decode(source): return source`  
After: `def python_decode(source): return 42`

Both have the same symbol and function signature, so a v0.4 `STRUCTURAL_DELTA_VERIFIED` receipt can be true even while behavior regresses. Also, byte-identical function bodies may act differently when moved between modules with different imports/globals, and unchanged Python imports can refer to a removed module or symbol. These are **different** from deciding what the best name means.

## Three read-only independent checks

1. `verification/naming_behavior.py::verify_naming_behavior_projection`: recomputes v0.4 exact Git candidate structure, reads before/after AST function/class/method bodies and stores normalized AST SHA-256 fingerprints for each declared responsibility placement. Reports executable-body differences, dynamic calls, state/import dependencies, module/identity changes, and exact source gaps. **An unchanged AST is not semantic proof**; outputs only `STATIC_BODY_MATCH_ONLY`, `HOLD`, or `REJECTED`, with `mutation_approved=False`.
2. `verification/naming_consumers.py::audit_naming_consumers`: scans bounded text and Python AST sources in the **two pinned Git trees**, including static imports, candidate dynamic/reflection usage and literal paths in docs/config/workflows/C++ text. Detects removed modules with stale static Python import consumers (`BLOCKED`) and retains unresolved internal imports, dynamic paths, scan-budget overflows and **external consumers not scanned** (`HOLD`). No worktree reads or execution. A clean bounded internal scan is **not** a global consumer closure proof.
3. `verification/naming_semantic_review.py`: constructs a *candidate-blind, not identity-blind* first-pass packet with actual Git AST declaration excerpts, anchored source refs and disclosed truncation. The reviewer first describes positive responsibility, negative boundary and a counterexample **without being shown the proposed new name**; a second pass compares KEEP and selected alternative. These findings are *claims*, not authenticated evidence of an independent second agent. Even a submitted `ACCEPT_FOR_REPLAY` remains `HOLD` until reviewer identity and reasoning are independently authenticated.

The combined `verification/naming_gates.py::evaluate_naming_safety_gates` re-runs all three against the exact candidate Git commit and emits one `NamingSafetyGateReport` with `BLOCKED/HOLD`, check obligations and nonauthorizing `mutation_approved=False`. It never accepts a caller-provided `PASS` receipt as a shortcut.

## Required future execution-contract proofs

- **Blinded semantic owner:** reviewer or genuinely independent evaluator who did not propose the candidate, authenticated by a trusted external provider. Compare positive and negative behavior contracts, not textual name overlap.
- **Controlled behavioral replay:** verified before/after expected input-output behavior, exceptions, side effects, imports and declared public API. Run only in a controlled CI runner; exact checked Git revisions, test set, toolchain and receipt identities must be bound. Do not run arbitrary discovered code on the controller machine.
- **Internal and external consumer closure:** static import rewrites, `__all__`, reflection (`__name__`, `__module__`), plugins and serialized class names; non-Python config/workflow/document references; external and dynamic consumers must be attested or explicitly protected by a verified compatibility shim.
- **Stable naming judgment:** KEEP remains the default for names that sufficiently delimit the actual responsibility. If splitting is justified, allow `EXTRACT_KEEP` without forcing a generalizing rename; compare post-extraction residual responsibility separately.
- **Transactional mutation:** isolated candidate changes only, complete before/after signed CI receipts, exact accepted HEAD, rollback and post-merge verification. The current modules cannot authorize or execute it. No workflow and no production code renamed in v0.5.

## Proof/coverage distinctions

| Finding | What it establishes | What it does not establish |
|---|---|---|
| `STRUCTURAL_DELTA_VERIFIED` | Selected responsibility declaration placement and signature | Runtime semantics, import resolution |
| `STATIC_BODY_MATCH_ONLY` | Compared Python AST bodies match syntactically | Globals, side effects, identity, dynamic runtime |
| `INTERNAL_SCAN_WITH_EXTERNAL_GAPS` | Bounded internal reference inventory had no blocking literal/static finding | External consumers, dynamic loads, arbitrary file types |
| Candidate-blind review packet | Reviewer can evaluate observed code before seeing candidate name | Reviewer independence or truth of prose |
| Combined `HOLD` | Evidence obligations are preserved without auto-change | A pass or mutation approval |

## Counterexamples covered in P0

- Identical signatures with changed return value / newly introduced side effect.
- Identical function body that accesses different module globals or imports after extraction.
- `getattr`, `import_module`, `globals`, `__import__`, pickle-like dynamic consumers.
- `from .collector import ...` or absolute `from diagnostics.collector import ...` surviving a file move.
- Markdown/config path literals; byte/file-budget overflow; untrusted working tree edits.
- GPT-provided fake source symbols, missing positive or negative boundary, omitted KEEP rebuttal, fake review URL and claimed reviewer PASS.
- Real `diagnostics/collector.py` negative control: an initial review packet is generated from current exact Git source, without showing an alternative name and without authorizing a change.

### Scope limit

Python AST and bounded internal textual scans are initial probes, **not** generalized semantic compatibility for C++/MOOSE, runtime plugins or remote consumers. Runtime replay, authenticated reviewer identity, external dependency provenance, and integration-HEAD validation are all still *unimplemented gates*, not silently waived checks. A separate authorized executor is required before any automatic change.
