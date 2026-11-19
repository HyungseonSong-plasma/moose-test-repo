# Common Code Analysis

This module **does not** duplicate the canonical `../graph/` models or
diagnostic source collectors. It uses the existing immutable `GraphSnapshot`,
`Context`, `Claim` and `Evidence`.

| Module | General capability |
| --- | --- |
| `impact.py` | Bounded forward/reverse dependency paths using `unfold_context`, with Scope/unresolved/truncation blockers |
| `findings.py` | Build unevaluated `Claim` objects with `SUPPORTS/REFUTES/QUALIFIES` Evidence links; validate references |
| `assessment.py` | Evidence-typed, fail-closed conditional review disposition and explicit verification obligations |
| `diff.py` | Compare stable Node/Edge semantics, source-bound Evidence changes, and Scope/coverage changes |

## Reuse

Use the same modules for code refactoring, CI validation, MOOSE object
retirement, branch retention and documentation impact. A domain-specific
query supplies roots, edge relation selectors, Evidence requirements and
verification obligations; core analysis remains unchanged.

**Safety:** analysis is read-only and never edits repository files or
workflows. A `CANDIDATE_FOR_VERIFICATION` is *not* authorization to
refactor, remove a branch, disable a check, or retire a MOOSE type.
Incomplete Scope, truncated traversal, unresolved targets, missing
Evidence kinds, unsupported assumptions, and REFUTES links lead to
`HOLD` or `BLOCKED`. A clean Graph diff or a passing test alone does
not establish semantic compatibility.

## Design boundaries

- `diagnostics/` collects exact-HEAD source facts and external
  Run/Attempt observations; `analysis/` evaluates evidence and impact.
- Node/Edge/Evidence/Claim/Scope/Context fields and all provider paths are
  unchanged.
- No generated `SAFE_DELETE` verdicts, automatic job removals, or
  mutations. Independent Verification gates remain required.
- `compare_graphs` ignores only Evidence links when comparing the
  Node/Edge *payload*; it reports Evidence identity changes separately.
