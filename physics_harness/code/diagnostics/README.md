# Diagnostics v0.1 — source-bound, read-only fact collection

**Status:** implemented D1–D5 core and first GitHub Actions Workflow static
collector. This is a general-purpose Graph evidence layer, **not a CI-specific
decision engine**. Issue [#721](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/721).

## Modules

| Module | Responsibility |
| --- | --- |
| `request.py` | `ScanRequest`, exact 40-hex Git SHA, include/exclude, roots, file/byte/time budget |
| `collector.py` | Logical IDs, `SourceProvider`/`Collector` contracts, `FactBatch`, `CollectionResult`, `run_scan` |
| `assemble.py` | `GraphAssembler`, deterministic merge, collision rejection, unresolved placeholder nodes, `GraphSnapshot` |
| `receipt.py` | `EvidenceReceipt` with per-file coverage, collector version, unresolved, scope completeness |
| `providers/git.py` | Tracked source inventory and exact blob bytes from a verified HEAD; no worktree fallback |
| `providers/workflow.py` | Static GitHub Actions Workflow/Job/Step/needs/event/run/uses source facts |

### Core invariants

- **Node identity** is revision-independent: repository + canonical type/path/
  qualified symbol. **Edge identity** includes source, target, relation and
  discriminator. The exact Git commit/blob and parser version reside in
  source-bound **Evidence**. Renames are separate logical objects until
  explicitly matched in verification.
- Collectors preserve source declarations as `SOURCE_DECLARED`; they must
  never invent `RUNTIME_OBSERVED`, `SAFE_DELETE`, `OVEREXECUTION`, a passing
  CI result, or a functional-equivalence Claim.
- GraphAssembler merges identical IDs by evidence **union**, rejects
  conflicting attributes or identities, retains multi-parent/cycles/parallel
  relations, and requires evidence for every diagnostics edge. Unknown
  references require a source-anchored `UNRESOLVED` witness.
- Scope completeness is **relative to the requested files and selected
  collector capabilities**. Parser failures, unsupported formats, unknown
  references, missing include patterns, source budget exhaustion, and dynamic
  workflow expressions produce `PARTIAL`, not false global completeness.
- Receipt statuses: `SCANNED`, `UNSUPPORTED`, `FAILED`, `SKIPPED_BUDGET`,
  `EXCLUDED`, `UNRESOLVED`. Files are identified by the exact Git HEAD and
  blob SHA; an unrelated GitHub Actions Run/attempt is **not** a valid proof of
  execution for this scan.

### Basic usage

Install the diagnostics dependency (`PyYAML`) from
`physics_harness/code/requirements.txt` and run:

```python
from pathlib import Path
from physics_harness.code.diagnostics import (
    GitSourceProvider, ScanRequest, run_scan,
)

request = ScanRequest(
    repository="HyungseonSong-plasma/moose-test-repo",
    revision="<exact-40-hex-local-HEAD>",
    includes=(".github/workflows/*.yml",),
)
result = run_scan(request, GitSourceProvider(Path(".")))
print(result.status, len(result.graph.nodes), len(result.graph.edges))
print(result.receipt.files)
```

The Workflow collector records relations such as `DECLARES_WORKFLOW`,
`DECLARES_JOB`, `DECLARES_STEP`, `NEEDS_JOB`,
`DECLARES_RUN_COMMAND`, `DECLARES_ACTION_USE`, and `DECLARES_TRIGGER`.
They express *YAML declarations only*, not successful workflow runs. PyYAML
BaseLoader preserves the literal GitHub Actions `on` key (avoiding YAML 1.1's
boolean conversion). YAML merge keys, duplicate keys and unsupported types
fail closed. Matrix expansion, expression evaluation, nested reusable
workflows, actual Runs/costs, and CI waste verdicts are **not implemented**.

### Validation and next steps

All acceptance tests are under `physics_harness/code/tests/` and run solely
through **Harness Code CI** using `pytest`. Existing FDEG scanners and
Physics workflows are unchanged. Future external GitHub Actions Run providers
must record `run_id`, `attempt`, source revision and artifact identities
separately, then connect to Claims in `../analysis/` without cross-HEAD
promotion or automatic deletion.
