# Common Code Analysis

This module **does not** duplicate the canonical `../graph/` models or
diagnostic source collectors. It uses the existing immutable `GraphSnapshot`,
`Context`, `Claim` and `Evidence`.

| Module | General capability |
| --- | --- |
| `impact.py` | Bounded forward/reverse dependency paths using `unfold_context`, with Scope/unresolved/truncation blockers |
| `findings.py` | Build unevaluated `Claim` objects with `SUPPORTS/REFUTES/QUALIFIES` Evidence links; validate references |
| `assessment.py` | Evidence-typed, fail-closed conditional review disposition and explicit verification obligations |
| `parameter_contract.py` | MOOSE input-to-C++ parameter comparison, separately scoped with unchanged source-only verdicts; original `assessment` exports retained |
| `diff.py` | Compare stable Node/Edge semantics, source-bound Evidence changes, and Scope/coverage changes |
| `understandability_adapter.py` | Transport Diagnostics data and optional human observations into the general metrics engine |
| `understandability_interpretation.py` | Interpret code-understandability indicators and caveats; no metric formulas or auto-refactor verdict |

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

## Target-centric coverage (P0)

Use `analyze_target_coverage(graph, receipt, target_id, required_paths=...,
unverified_surfaces=...)` to inspect directly attributable source evidence,
unscanned required paths, unresolved Scope and other incomplete files.
The caller must declare the required exact paths. Cross-Scope or cross-HEAD
Graph/Receipt combinations are rejected, not silently aggregated.

`complete_within_requested_scope` means only that the declared source files
were scanned with the enabled collectors. Even `COMPLETE` here cannot prove
global caller-zero, Factory linkage, generated-input closure or runtime
behavior. Accordingly `global_consumer_closed` is **always False** and
`retirement_disposition` is **always HOLD** at this stage.

Unknown Scope reasons and incomplete files remain in the report even when
not adjacent to the target, because their relevance is unproven.
This deliberately does not implement `ScanRequest.roots` filtering, a
target-consumer universe certificate, or semantic equivalence verification.
Those require separately evidenced later contracts.
