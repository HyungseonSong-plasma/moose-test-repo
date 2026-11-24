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
| `usage_matrix.py` | Read-only multi-target one-hop Usage Matrix; selected typed relations, source witnesses, scoped coverage, conservative screening, JSON and Markdown views |
| `adapters/lucidity_adapter.py` | Transport Diagnostics data and optional human observations into the general metrics engine |
| `adapters/lucidity_interpretation.py` | Interpret code-understandability indicators and caveats; no metric formulas or auto-refactor verdict |

`adapters/` contains the specialized integrations. Direct legacy adapter module
paths have been retired; the public Analysis API and Diagnostics providers remain unchanged.

| `usage_matrix.py` | Read-only multi-target one-hop Usage Matrix; selected typed relations, source witnesses, scoped coverage, conservative screening, JSON and Markdown views |

## Usage Matrix v0.1

`build_usage_matrix(graph, receipt, targets, relations, ...)` groups adjacent references
without introducing a new Graph model or a domain-specific deletion rule. Relation
selection and direction are explicit; all unclassified incident edges are blockers
unless the caller declares their relations as known non-consumer relations.

Example for source-declared MOOSE consumers (not a global caller census):

```python
from physics_harness.code.analysis import UsageRelation, build_usage_matrix

relations = (
    UsageRelation('DECLARES_TYPE_USE', 'DIRECT_DECLARATION'),
    UsageRelation('MAY_GENERATE_INPUT', 'GENERATED_CANDIDATE'),
    UsageRelation('HISTORICAL_ASSERTS_TYPE', 'HISTORICAL_REFERENCE'),
    UsageRelation('DECLARES_GENERATOR_TEMPLATE_CANDIDATE', 'TEMPLATE_CANDIDATE'),
)
matrix = build_usage_matrix(
    diagnostic.graph, diagnostic.receipt, moose_type_ids, relations,
    required_paths=audited_paths,
    unverified_surfaces=('external_consumers', 'generated_inputs', 'native_runtime'),
    ignored_relations=('DECLARES_MOOSE_REGISTRATION', 'DECLARES_PARAM_CONTRACT'),
)
json_data = matrix.to_dict()   # JSON serializable, identity/evidence retained
table = matrix.to_markdown()  # compact human review view
```

The caller must declare audited paths and unresolved surfaces; no omitted path
is considered scanned. `RETAIN` means a source-bound reference exists and
direct deletion is not allowed, **not** that runtime use was observed.
`REVIEW_CANDIDATE` only means no identified consumers under the declared
relation/scope policy; it never means zero global callers or safe removal.
`HOLD` preserves missing evidence, dynamic references, partial scans,
unclassified edge kinds, and other verification obligations. The result
always reports `global_consumer_closed=False`, `mutation_approved=False`,
and `safe_to_delete=False` on all rows. One-hop aggregation does not prove
transitive callers, alternative physics semantics or actual Native execution.

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

## File reference resolution (#867)

`resolve_file_references(graph, receipt, GitSourceProvider(root), bases_by_edge=...)` resolves observed file-reference candidates against the exact checked-out Git revision. Supply an explicit tuple of `REPOSITORY_ROOT` and/or `OWNER_DIRECTORY` for each evidence edge; missing base declarations are UNRESOLVED. The same literal in two documents can resolve differently. No basename search or ambient working-directory fallback. Multiple tracked candidates are AMBIGUOUS, absent exact paths MISSING, nonregular targets NON_REGULAR, and dynamic or escaping paths UNRESOLVED. RESOLVED_CANDIDATE identifies an exact tracked path/blob under the supplied base assumptions, not executable use. Target coverage (including OUT_OF_SCOPE) is independent of path existence. The original Graph and Receipt are unchanged; the report is an analysis projection, not global closure or deletion approval. Existing source metadata verification is checked and receipt file blobs must agree with the Git inventory; independent parser replay and runtime interpretation remain outside this contract.
