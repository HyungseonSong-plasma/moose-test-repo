# Code Diagnostics — module boundaries

**Status:** file skeleton only. No collectors, parsers, Git readers, execution
entrypoints, or diagnostic results have been implemented.

The purpose of `diagnostics/` is **read-only collection of source-bound facts**
for the shared Code Graph. It does not assess semantic compatibility, approve
refactors, or authorize code retirement.

| Module | Owner | Future responsibility |
| --- | --- | --- |
| `source.py` | Source identity | Exact Git revision, tracked files and source/blob provenance; no unstated worktree fallback |
| `extractor.py` | Extractor interface | Language/file-type-specific fact extraction contracts and extension points |
| `collector.py` | Collection orchestration | Dispatch source inputs to extractors; combine and validate Node/Edge/Evidence with GraphSnapshot |
| `result.py` | Diagnostics output | Report source scope, unresolved references, unhandled formats and coverage limitations without a PASS/DELETE verdict |
| `__init__.py` | Package surface | Export only stable, implemented APIs; empty until implementation |

## Ownership and evidence rules

- `../graph/node.py`, `edge.py`, `evidence.py`, `claim.py`,
  `scope.py` and `context.py` **own the canonical data model**.
  Do not duplicate these models under `diagnostics/`.
- Existing FDEG guards remain independent until an explicit, verified adapter
  is implemented. Their presence is not evidence of automatic compatibility.
- Static declarations are `SOURCE_DECLARED` (or `INFERRED`), **never**
  `RUNTIME_OBSERVED`. Unresolved imports, dynamic dispatch and incomplete
  sources must remain visible.
- `diagnostics/` extracts facts; `../analysis/` evaluates their meaning.
  Transition plans and changes belong to `../refactor/` and `../delete/`;
  acceptance checks belong to `../verification/`.
- Code changes and tests stay inside `physics_harness/code/`; tests go in
  `../tests/` and are run by the dedicated Harness Code CI
  (`python -m pytest -q physics_harness/code/tests`).

## Proposed implementation sequence

1. Implement exact-revision source acquisition in `source.py`.
2. Define extractor input/output and registration boundary in `extractor.py`.
3. Implement collection, GraphSnapshot validation and unresolved reporting in
   `collector.py` and `result.py`.
4. Add language-specific extractors **only when needed**, with positive and
   negative controls in `../tests/`. No speculative `python_ast.py`,
   `cpp.py` or FDEG adapter is created at this stage.

Issue: [#721 — harness_code 개발](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/721).
