# FDEG HEAD-pinned scan/index reuse v0.1

**Track:** #718, PR #719. **Applies to:** Structural v0.3, Functional v0.2, Transition v0.1. **Safety:** remains `NO_CALLER_ZERO_OR_RETIREMENT_VERDICT` and `SAFE_DELETE=HOLD`. This change is a *performance optimization*, not new proof of consumer completeness or runtime equivalence.

## Problem: same source repeatedly read and parsed

Structural builds a tracked-source snapshot and source-evidence graph. Functional independently reconstructs Structural; Transition independently reconstructs Functional (which re-verifies Structural); the pre-retirement receipt constructs all three again. Repeated repo traversal dominated the validate Job. In the prior CI run #44567705611, Functional P0 took ~105 s, Transition P0 ~87 s, A–D P0 ~106 s and code7 evidence capture ~52 s; Structural standalone took ~0.02 s in its tiny isolated unit fixture. The full-repo corpus differs from that fixture. These durations include tests, not just Scanner execution.

## Implementation

When `FDEG_CACHE_DIR` is set to an absolute directory **outside the repository**, `fdeg_structural.scan()` uses two read-through layers:

1. **Per-target graph cache** — one previously built, complete `fdeg.structural.v0.3` report for the same exact `repository_head`, target, source root, Python version and implementation fingerprint. On hit, **no repository file listing, read or AST analysis** is repeated. Cache entries preserve existing graph IDs, edges, errors, blockers, witness lines and safety fields byte-for-byte.
2. **Shared tracked-source index** — one compressed, full set of decoded tracked file contents, Git Blob SHA values and read errors per exact HEAD and Scanner implementation. A cold *different* target reuses this snapshot instead of doing another complete tracked-file read. The cached source path set and **every Git Blob SHA** are checked against the current HEAD's `git ls-files --stage` metadata; this is a metadata-only path census, not a re-read or re-parse of the files. That target still computes its own graph, including source-dependent unknowns; this deliberately does not silently restrict the candidate corpus to a lexical substring match.

The first target on a new HEAD performs the normal full scan to populate both layers. A new target with no graph cache still parses the shared source set. **True target-scoped AST preindexing is not claimed or implemented here**; it needs separate source-role/completeness gates to avoid false caller-zero conclusions.

### Invalidation and failure behavior

Cache identity includes exact Git HEAD, resolved repository root, target (for graph entries), Python implementation/version and SHA-256 of the actual Structural, Enrichment and cache-module code bytes. Each cache read first checks `git rev-parse HEAD` and `git status --porcelain --untracked-files=no`.

- A requested different `--expected-head`, or modified tracked files with an explicit expected head: **fail closed**.
- Dirty tracked worktree with no expected head: **do not use cache**, fall back to ordinary source scanning.
- Scanner implementation change, new Git commit, different repository/target: cache key changes; a new entry is generated.
- Missing, invalid or corrupt JSON/gzip, wrong envelope, mismatching cache graph ID/SHA, or even a rehashed source-index payload with a missing/changed tracked Git blob: **cache miss**, reconstruct from source. Failure to write the optional cache does not fail a valid scan.
- No `FDEG_CACHE_DIR` or non-Git/synthetic workspace: existing scan path and graph shape preserved.

The cache is **runner-local scratch data**, never a reusable CI evidence artifact and never an authorization or trust substitute for independent physics evidence. Fresh exact-HEAD Git identity, Structural/Functional/Transition P0, Native independent oracle and Coverage gates remain mandatory. The offline pre-retirement S/F/T archive is a separate immutable deliverable and is never sourced from a different HEAD.

### CI wiring

The canonical template `physics_harness/workflow/definitions/general-ci.yml` and generated workflow `.github/workflows/ci.yml` use:

```yaml
validate:
  env:
    FDEG_CACHE_DIR: /tmp/fdeg-index-${{ github.run_id }}-${{ github.run_attempt }}
```

All steps in the same `validate` Job share the directory. A new Action run/attempt uses a fresh directory; no cache is transferred across machines or commits. `tests/test_fdeg_scan_cache.py` runs as its own P0 step, outside the general pytest rediscovery, and explicitly tests cache HIT, different-target source-index HIT, new HEAD, tracked-worktree dirtiness, code fingerprint invalidation and corrupt source/graph cache rebuild.

### Acceptance and benchmark

The PR is accepted for this optimization only if:
- original Structural/Functional/Transition/A–D and new scan-cache P0 succeed at the same exact PR HEAD;
- Repository CI and SOL integration complete successfully; canonical and generated workflow blobs match;
- independently compare all report `graph_id` values with opt-in cache off/on at the same source HEAD (at minimum the P0 fixtures do this for isolated repositories);
- observe runner logs with `FDEG_STRUCTURAL_CACHE=HIT`, `FDEG_SOURCE_INDEX=HIT` and report measured elapsed-time difference rather than assuming a particular speedup.

**Important limitation:** This v0.1 eliminates repeated whole-repository reads and repeated full scans of the **same target**; it does not remove the first HEAD-wide source index build or first AST scan for each newly encountered target. Achieving complete target-only parsing requires a separately validated per-file parser index without omitting dynamic/generated/external candidates.
