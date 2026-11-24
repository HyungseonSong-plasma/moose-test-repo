# 조사#1 — Harness Code / Libs self-analysis

**Status:** RESEARCH / preliminary investigation; not an architecture authority, implementation plan or mutation approval.  
**Scope:** `physics_harness/code/`, `libs/`; Python implementation, package entry points and tests.  
**Source:** [main@2bf977e](https://github.com/HyungseonSong-plasma/moose-test-repo/commit/2bf977e17fa2e4eb84b24bce51a717bc76be60f7) (2026-11-24).  
**Historical context:** #758 (closed, earlier self-analysis), #769/#770 (Naming), #771 (Analysis adapters), #772 (Usage Matrix). This survey does not reopen or supersede their acceptance decisions.

## 1. Evidence and limitations

Existing [Harness source scan #45411795969](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45411795969), attempt 1, was reused instead of launching duplicate CI. Request commit `838077fe94efc8eaa1b44bb5c974a6cf11183eb9`; scanned source SHA is the main SHA above, not the request commit. Request ID `physical-eV-retirement-impact-20261124`; collectors cpp, moose_input, python_ast, workflow. The request is broader than this survey.

[Artifact #14928832103](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45411795969/artifacts/14928832103), `harness-source-scan-45411795969-1`, SHA-256 `f91cf4bd3a761b13dfc76a8816595ee323fdc0d08f3f506ebccd5e4dced01bc7`; includes request, graph, evidence receipt, verification receipt and summary. Workflow checkout, exact-HEAD assertion, scan and upload succeeded. Full run: 973 SCANNED, 226 UNRESOLVED; 103,855 nodes, 316,742 edges, 317,941 evidence; PARTIAL/UNVERIFIED, 1,896 unresolved entries, zero verification failures. No claim of global consumer closure or semantic equivalence.

Target-scope census: 110 Python files, 91 SCANNED / 19 UNRESOLVED (19 path-local unresolved entries in run log). The preceding survey reported 892 functions, 125 classes, 1,036 import candidates and 6,676 call candidates. Its derived static module resolution reported 721 internal import candidates, 278 distinct cross-file edges, 168 excluding tests, and a 22-module SCC including deferred imports; no SCC under its top-level-only filter. These derived figures are preliminary, not outputs of the canonical dependency verifier; the resolution script and exact witness list have not been preserved here. They require reproducible recheck before being used for acceptance.

## 2. Growth census

Tracked Python files only; sizes are Git tree byte counts, not LOC. Baseline [4f873e7](https://github.com/HyungseonSong-plasma/moose-test-repo/commit/4f873e71f8503943c9fce2dd30fcc96c28d6f631) (2026-11-22, after HU bridge retirement).

| Area | Baseline | Current | Delta |
|---|---:|---:|---:|
| graph | 8 | 8 | 0 |
| diagnostics | 12 | 12 | 0 |
| analysis | 9 | 15 | +6 |
| refactor | 3 | 5 | +2 |
| verification | 3 | 16 | +13 |
| delete | 1 | 1 | 0 |
| tests | 23 | 43 | +20 |
| libs | 5 | 9 | +4 |
| code package init | 1 | 1 | 0 |
| Total | 65 | 110 | +45 |

Python bytes: 370,626 -> 683,226 (+84.3%); files +69.2%. Verification and tests account for 33/45 added files. Naming-related implementation (including evolution, JUnit comparison and pytest revision runner): 15 files / 159,138 bytes; test_naming_*: 18 files / 123,371 bytes. These categories are descriptive, not evidence of unnecessary functionality.

## 3. Actual responsibility boundaries

- Graph: canonical identity, evidence, claims, scope, traversal. KEEP baseline.
- Diagnostics: exact Git source and external observations; source fact collection and receipt generation. Source integrity is verified during assembly.
- Analysis: impact, target coverage, Usage Matrix, findings and contextual interpretation; adapters transport source facts to the independent Lucidity engine.
- Refactor: KEEP/CHANGE alternative review, naming recommendations and evolution.
- Verification: source consistency, dependency contracts, candidate placement, AST body projection, consumer search, semantic review, reviewer authority, execution/JUnit replay and artifact custody.
- Libs: canonical `code_lucidity` engine owns metrics, not decisions. `code_understandability` is an import bridge. KEEP numerical model.
- Tests: preserve separate positive/negative controls and independent evidence responsibilities.
- Delete: placeholder, no automatic deletion capability.

## 4. Candidate register (investigation only)

Paths below are relative to `physics_harness/code/` unless stated otherwise. Source anchors refer to the pinned revision above. All CHANGE alternatives remain unapproved; compare with KEEP.

| ID | Finding / source anchor | Candidate direction | Preserve / next discriminator |
|---|---|---|---|
| R01 | Git tree handling duplicated in `diagnostics/providers/git.py:29-65`, `verification/naming_boundary.py:74-94`, `verification/naming_consumers.py:59-77`; other private `_git` calls in evolution, candidate, provenance and pytest runner | Reuse provider-owned revision inventory and ancestry primitives; no new library by default | Exact SHA/blob, historical vs HEAD semantics, regular file filters, error and budget behavior; compare actual callers and negative controls |
| R02 | `verification/naming_gates.py:51-113` calls candidate and behavior; `naming_behavior.py:106-175` calls candidate again; `naming_candidate.py:55-201` invokes boundary; `naming_semantic_review.py:84-142` separately invokes baseline KEEP boundary. Boundary also reads source for budget then reads again in symbol inventory | Reuse immutable source and parsed AST within trusted invocation; measure duplicate reads and parsing | Never trust arbitrary caller-supplied PASS; independent blind review and option-specific judgments remain distinct; verify identical statuses, blockers, witnesses and budgets |
| R03 | `analysis/usage_matrix.py:166-184` builds adjacency once but invokes `impact.py:108-201` per target, rebuilding node/evidence/file indexes and scanning all edges | Shared query indexes within a multi-target analysis; preserve standalone API | Source-scope binding, missing/unresolved evidence, stable ordering and one-hop semantics; benchmark actual same-graph workloads |
| R04 | Seven independent AST parsing sites: python_ast, evolution, dependencies, naming_boundary, naming_behavior, naming_consumers, naming_semantic_review. Diagnostics detects encoding and uses type_comments; others have differing contracts | Compare common decode/parse/declaration/import primitives, not merge judgment layers | Encoding, type comments, nested symbols, relative imports, dynamic references and existing evidence identity; test differences before unifying |
| R05 | `diagnostics/assemble.py:158` imports verification package; `verification/__init__.py` eagerly imports 13 submodules. `refactor/naming.py:462` imports naming provenance inside function | Reduce initialization coupling while maintaining consistency checks and public exports | Submodule import alone still executes package init; prove fresh-process import behavior and source verification parity |
| R06 | Long/high-branch functions and deep nesting concentrate in Verification | Function-local simplification where responsibility and preserved behavior are demonstrated | Branch count is not a quality verdict; keep validation/error order and negative tests |
| R07 | `tests/test_naming_boundary_repository.py` and `tests/test_naming_semantic_review_repository.py` repeat HEAD/provider/citation/case setup | Reuse fixtures without removing distinct tests | Preserve actual Git witness and independent test assertions; inspect existing conftest |
| R08 | `verification/naming_actions.py:34-122` and `naming_review_authority.py:73-98` implement bounded REST reads; diagnostics GitHub Actions provider injects GET | Compare common transport mechanisms | Review redirects prohibited vs signed archive redirects; no credential forwarding; attempt and pagination semantics |
| R09 | Ten import-only bridges (1,632 bytes): four libs/code_understandability, four analysis lucidity/understandability, two verification naming_replay paths | HOLD; inventory and decide compatibility lifecycle | Explicit compatibility tests and unknown external/dynamic/serialized consumers; no deletion |
| R10 | No demonstrated Graph-model defect requiring redesign | KEEP baseline | Revisit only with counterevidence |
| R11 | Lucidity engine remains independently owned | KEEP baseline | No new score, formula or experiment prerequisite |

R01–R05 are priority **investigations**, not authorized refactors. R06–R08 secondary; R09 HOLD. No automated universal priority score.

### Complexity screening (preliminary Graph-derived)

Non-test function count 294. Screening thresholds branch >=20 and max branch nesting >=5 are investigative, not acceptance criteria. Reported counts by area: graph 0/0, diagnostics 6/3, analysis 4/2, refactor 4/2, verification 10/10, libs 0/0. Examples: verify_naming_boundary 54 branches; verify_naming_candidate 53; _scan_revision nesting 9. Reproduce exact symbol/line/metric evidence in next survey. No direct Lucidity engine evaluation yet.

R03 theoretical edge visits for T targets: approximately (T+1)*316742 vs a single full adjacency construction plus incident-edge visits. This counts only full edge passes, not memory cost, all processing, or measured speedup.

## 5. Next investigation requirements

1. Confirm exact source SHA and preserve original receipts; use existing Harness functions rather than introduce another analysis engine.
2. Reproduce target-local structural, dependency and Usage Matrix evidence, recording exact source witnesses and unresolved surfaces. Compare syntactic candidates with independently resolved module references; no runtime closure inference.
3. For R01–R05 identify common vs specialized responsibilities, consumers, preconditions, evidence contracts, repeated-work counts and counterexamples. Compare KEEP against smallest internal improvement; no folder or model change by default.
4. Directly evaluate existing Lucidity and Planning APIs at the pinned source, retaining unknowns and required checks. No fabricated aggregate metric.
5. Measure candidate-specific performance only where relevant; establish baseline and independent parity controls before proposing implementation.
6. Keep code, workflows, CI policy, public API and tests unchanged during research. Approval for this document/PR is not approval to implement any candidate.

**Survey result:** RESEARCH continues. No source mutation, refactor, deletion, test removal, CI trigger change, or merge authorized. The existing scan was reused; no fresh clone or pytest replay was performed for this survey. Static call/import candidates are not resolved runtime behavior. External consumers and semantic compatibility remain unverified.
