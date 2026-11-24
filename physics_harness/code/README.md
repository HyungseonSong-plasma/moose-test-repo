# Code lifecycle — source evidence, analysis and planning

`physics_harness/code/` provides reusable, read-only foundations for inspecting
source code and repository automation. Its collectors currently cover selected
Python, C++, MOOSE input, JSON and GitHub Actions Workflow forms; the architecture
can support other languages, but **unimplemented collectors are not claimed**.

| Component | Implemented responsibility |
| --- | --- |
| [`graph/`](graph/README.md) | Revision-independent Node/Edge identity, source-bound Evidence and Claim, Scope, deterministic context traversal |
| [`diagnostics/`](diagnostics/README.md) | Exact Git revision/Blob source scanning, bounded collectors, source Graph/Evidence receipts and partial-coverage reporting |
| [`analysis/`](analysis/README.md) | Source-bound findings, impact and coverage, exact-inventory file-reference resolution, code-understandability interpretation and MOOSE parameter-contract analysis |
| [`refactor/`](refactor/README.md) | Strategy-neutral KEEP/CHANGE alternatives, evidence/constraint checks and explicit follow-up verification obligations |
| [`verification/`](verification/README.md) | Graph/receipt consistency, configurable source dependency checks and before/after verification planning |
| `delete/` | Reserved: no automatic source-retirement or deletion engine is implemented |
| `tests/` | Local regression tests for implemented Code lifecycle components |

The independent [`libs/code_lucidity/`](../../libs/code_lucidity/README.md)
engine defines and computes metrics associated with code understandability.
Human evaluations are optional evidence, not a metric prerequisite.
`analysis/adapters/lucidity_adapter.py` transports source facts and results;
`analysis/adapters/lucidity_interpretation.py` interprets their meaning.
Planning, not the engine, decides how to compare refactor options.

## Scope and evidence guarantees

The [Code Graph](graph/README.md) is a directed multigraph whose stable logical
nodes and edges can have multiple parents, parallel relations and cycles.
Evidence records *where* source and runtime observations came from; Claims
link evidence with support/refute/qualify roles and remain conditional.

`diagnostics.run_scan()` selects bounded source inputs and collectors.
Built-in source collectors include `workflow`, `python_ast`, `cpp` and
`moose_input` and `json`. The injected read-only `GitHubActionsRunProvider` records
external Run/Attempt observations separately; it does not invent execution
from static Workflow declarations. Candidate import, call, and MOOSE type
edges are **syntactic candidates**, not resolved runtime dependencies. JSON, Python and MOOSE HIT file-reference candidates can be analyzed using explicit repository-root or owner-directory bases against the exact Git inventory. The resolution result is a candidate path/blob, not runtime use.

A `COMPLETE`/source-`VERIFIED` result means only that the requested scope
was collected and its metadata is consistent. Unsupported constructs,
dynamic references and missing source retain `PARTIAL` or `UNVERIFIED`
states. Source integrity does not establish global consumer closure,
semantic equivalence, native runtime compatibility or safe deletion.

## Data flow

```text
Diagnostics -> Graph and source evidence
            -> Code-understandability metrics (via Adapter) -> Analysis interpretation
            -> Refactor Planning (KEEP / CHANGE and verification obligations)
            -> Verification after an approved code change
```

Analysis and Planning are **read-only**. They do not execute edits, approve
mutations, remove old code, or rank changes using a hard-coded universal
refactoring strategy.

## Tests and CI ownership

`Harness Code CI` runs the Code self-tests when files under
`physics_harness/code/**` or the dedicated Workflow change:

```bash
python -m pytest -q physics_harness/code/tests
```

A change solely under `libs/code_lucidity/**` does **not** currently trigger this
path-filtered Harness Code workflow. Repository CI owns its shared integration
checks on pull requests. Changes to CI routing or trigger ownership are
separate decisions; documenting current behavior does not modify them.

Canonical paths are `libs/code_lucidity/`, `analysis/adapters/lucidity_adapter.py`,
and `analysis/adapters/lucidity_interpretation.py`. Use these canonical paths or the
public Analysis package exports; the superseded module paths have been retired.
Public numeric measurement types and
functions retain their explicit understandability vocabulary; this path rename
does not introduce an aggregate score or change a metric formula.
