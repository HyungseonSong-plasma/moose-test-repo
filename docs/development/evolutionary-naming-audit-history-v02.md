# Evolutionary Naming Audit — exact Git history evidence v0.2

**Scope:** source-backed structural history and existing-delegation reconnaissance.
**Issue:** #769; Draft PR #770. **No code rename or extraction executed.**

## Concrete negative control

GitHub's immutable objects were inspected for
`physics_harness/code/diagnostics/collector.py` at four commits:

| Revision | Added provider evidence | Existing top-level responsibility surface |
|---|---|---|
| `bf0589ab361c` | Workflow collector | `Collector`, `SourceProvider`, `run_scan` |
| `9603bdf41618` | Python AST collector | Same declarations |
| `25aa9a263ecf` | C++ and MOOSE Input collectors | Same declarations |
| `4f873e71f850` | Python/C++/MOOSE Input providers remain distinct files | Same declarations |

See `experiments/evolutionary_naming_audit/historical_collector_evidence.json`
for exact commit SHAs, file Blob SHAs and individual source-line references.

**Observed:** provider imports increased while generic declarations remained.
Current `Collector(Protocol)` declares `supports` and `collect`; classes
`PythonAstCollector`, `CppSourceCollector`, `MooseInputCollector` live in
`diagnostics/providers/` and implement those method names. The existing
`collector.py` is not an obvious redundant language-specific owner.

**Interpretation:** this provides an evidence-based **KEEP_CONSIDERATION**
negative control and no justification for inventing another `libs/` layer.
It does not establish that the name *must* be retained, prove semantic stability,
or establish that no extraction can ever be beneficial. `KEEP` as an actual
naming decision still requires an independent name/role assessment.

## Implemented measurement contract

- `GitSourceProvider.read_at_revision(revision, path)`: accepts an exact 40-hex
  Git commit, resolves an exact tracked regular file via `git ls-tree`, reads
  verified Git Blob bytes; no worktree fallback. Missing historical objects
  (including in CI shallow clones), symlinks, other revisions and invalid paths
  fail closed.
- `refactor/evolution.py`: AST-only declarations, import aliases, local
  syntactic protocols, cross-file implementation seams, and before/after
  snapshots. No target name or README in responsibility inference.
- `audit_git_history()`: verifies ancestor relationship, reads exact objects,
  compares top-level declarations/imports and reports newly observed
  delegation. Unresolved names, implementation semantics and external
  consumers are independent gates. `mutation_approved` always False.
- P0: synthetic two-commit local Git repository proves old/new snapshots are
  read from Git objects even if the worktree is subsequently modified; false
  method match, wrong module, cross revision, dynamic import, path traversal,
  unrelated lineage and move/identity uncertainty have negative controls.
- Actual checked-out repository CI checks the current HEAD `collector.py`
  and its existing providers. It does **not** claim CI replay of the historical
  commit source bytes; the historical manifest above is a pinned, externally
  inspected receipt that needs real prior Git objects for full replay.

## Next blocker

Do **not** use added imports or matching public declarations as a semantic
Definition or as an automatic Rename decision. The next independent gate must
resolve actual responsibility changes, consumer/reference closure, name-fit
judgment, and verified candidate before/after semantics. A source-only
`KEEP_CONSIDERATION` is only a safe hypothesis for GPT to examine.
