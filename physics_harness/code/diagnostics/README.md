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
| `receipt.py` | `EvidenceReceipt` with per-file coverage, collector version, file/byte/time budget, attempt count, elapsed time, unresolved and scope completeness |
| `providers/git.py` | Tracked source inventory and exact blob bytes from a verified HEAD; no worktree fallback |
| `providers/workflow.py` | Static GitHub Actions Workflow/Job/Step/needs/event/run/uses source facts |
| `providers/python_ast.py` | Python syntax-only declaration, import, call-site and name/attribute reference candidates |
| `providers/cpp.py` | C++ class/include/Factory macro source-declaration candidates |
| `providers/moose_input.py` | MOOSE HIT `.i` blocks, type reference and unresolved include syntax |
| `providers/json_source.py` | Strict JSON string-value file-path candidates with JSON Pointer and exact source witnesses |
| `providers/github_actions.py` | Read-only external Run/Attempt/Job/Step observation with exact source SHA and pagination controls |


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

### Python AST source facts (P1/P2)

Select `collectors=("python_ast",)` and `includes=("src/*.py",)` to
scan tracked Python files at the exact local HEAD. The built-in registry now
includes `python_ast`, alongside the existing `workflow` collector.

The Python AST collector emits `DEFINES`, `IMPORTS_CANDIDATE`,
`CALLS_CANDIDATE`, and `REFERENCES_CANDIDATE` edges with source-line/blob
Evidence. `python_function`/`python_class` declarations include LOC,
branch count and maximum branch nesting, with nested definitions excluded
from the containing declaration's metrics. Python's AST parser is used
directly; no source module is imported or executed.

**Static candidate != resolved target or runtime call.** No import or
name binding resolution is promised. The identifiers of candidate
specifier nodes describe *syntactic names*, not a confirmed repository
or external function identity. Dynamic reflective calls such as
`getattr`, `__import__`, `eval`, and `importlib.import_module`
surface an explicit unresolved target and `PARTIAL`. Unsupported syntax
and invalid source encoding fail closed as `FAILED` coverage. Neither
Collector claims code is unused or safe to delete.

The default `ScanRequest.collectors` remains `("workflow",)`, so existing
call sites keep their previous behavior. No Graph model, public field or
folder was moved.

### C++ and MOOSE source linkage

To inspect a bounded exact-HEAD source set, explicitly request
`collectors=("cpp", "moose_input")` with matching `.C`, `.h`, and
`.i` path patterns. The collectors use the same canonical
`moose_type` Node ID for a literal C++ Factory registration and a
literal input `type = ...` declaration. GraphAssembler unions the
independent source Evidence from both files.

Relations are deliberately named `DECLARES_MOOSE_REGISTRATION` and
`DECLARES_TYPE_USE`, not `RUNTIME_INSTANTIATES` or `SAFE_DELETE`.
Class inheritance and `#include` are candidate relations. The narrow
C++ textual extractor cannot prove namespace resolution, macro expansion,
conditional compilation, include resolution, build linkage, or runtime
registration. Unsupported/preprocessed registration forms and conditional
source are `PARTIAL`. The MOOSE HIT collector is a conservative
block/type/include parser. Dynamic values, includes, duplicate/unclosed
blocks and unsupported syntax produce `PARTIAL` or `FAILED`, never false
complete coverage. More complex syntax needs a separate capability test
before this collector may be used to qualify deletion.

### External GitHub Actions runtime observations

`GitHubActionsRunProvider(fetch_json)` reads actual REST Run/Attempt and
paginated Job/Step payloads using an **injected read-only GET callable**
(which may use a GitHub App or a token-authorized REST client).
It intentionally does **not** implement file `Collector` or inject fake
Git blobs into `SourceProvider`. Its `collect_run(request, run_id, attempt)`
returns a `CollectionResult(FactBatch, status)` that can be assembled with
source facts using the existing `GraphAssembler`. The caller must pin
`request.revision` to the exact run's source SHA. A mismatch raises and
cannot be relabelled as a successful observation.

```python
from physics_harness.code.diagnostics import (
    FactBatch, GitHubActionsRunProvider, GraphAssembler,
)

# source_result = run_scan(request, GitSourceProvider(...))
# fetch_json(url) must perform an authenticated, read-only REST GET.
observed = GitHubActionsRunProvider(fetch_json).collect_run(request, run_id, 1)
combined = GraphAssembler().assemble(
    request,
    (
        FactBatch(nodes=source_result.graph.nodes,
                  edges=source_result.graph.edges,
                  evidence=source_result.graph.evidence),
        observed.batch,
    ),
    source_result.receipt,
)
```

Run, Job and Step conclusions are independently preserved as
`RUNTIME_OBSERVED` source attributes; the Workflow-level `success`
status cannot turn a `skipped` Job into PASS. API page gaps, mutation
during retrieval, in-progress status and missing metadata produce
`PARTIAL`/unresolved, including in the combined Graph scope. A failed
Run fetch returns `FAILED` without invented runtime Evidence.
This provider does not discover changeset diffs, checkout SHA from logs,
Required Checks, actual build/test identity, external artifact custody or
time cost. Those remain separate follow-on obligations.


### Generated MOOSE source candidates in Python

The Python AST source collector recognizes literal `type = X` lines
in Python strings and f-string literal fragments. Literal names share
the exact canonical `moose_type` identity used by `cpp` registrations
and `moose_input` declarations. New relations distinguish:
- `MAY_GENERATE_INPUT`: a literal inside a Python `return` expression;
- `HISTORICAL_ASSERTS_TYPE`: a literal in an `assert` expression;
- `DECLARES_GENERATOR_TEMPLATE_CANDIDATE`: other literal strings.

A Python string is not evidence the program actually generated, loaded
or executed an MOOSE input. Rendered f-strings with formatted values are
`PARTIAL` with `PYTHON_GENERATOR_RENDER_UNVERIFIED` even if their
literal type is known. Nonliteral `type = {variable}` values generate
an unresolved placeholder, rather than a fabricated `moose_type`.
Docstrings do not count as generators. No runtime evidence, binding
resolution or `SAFE_DELETE` verdict is created.

### JSON source facts (opt-in, #867)

Request `collectors=("json",)` with `includes=("*.json",)` (or combine with existing collectors). `JsonSourceCollector` validates strict UTF-8 JSON and emits `REFERENCES_FILE_CANDIDATE` edges from the source file to a `file_path_specifier` node for portable path-shaped whole-string values. Evidence preserves the RFC 6901 JSON Pointer, decoded literal, 1-based physical line, 0-based Unicode character column of the opening quote, Git revision/blob and parser version. Multiple occurrences remain separate edges; specifier IDs are stable across revisions and source documents. No key-name policy, numeric-array graph expansion, or new dependency is introduced.

The v0.1 lexical predicate covers ASCII relative path-shaped strings with a letter-starting suffix (including bare filenames and `./`/`../` segments). It does **not** resolve the path against Git inventory or a working directory; basename, URI, prose, key-name, extensionless, other string and runtime interpretation remain outside the reference claim. Obvious nonportable/glob/template paths with suffixes are unresolved, not resolved target nodes. Depth (128) and reference count (10,000 per file) limits return PARTIAL without partial document facts. Duplicate keys, invalid encoding/syntax and nonstandard constants fail closed. COMPLETE only means the declared syntax/lexical observation contract succeeded, not file-reference closure. The `json` collector is accepted by the existing on-demand Harness scan route; default collectors, trigger events, Physics CI and Graph model are unchanged.
