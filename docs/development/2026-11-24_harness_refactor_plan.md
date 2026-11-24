# Harness Code / Libs — Refactor 계획안

**Status:** RESEARCH / proposal v0.3 — Accuracy, Responsibility & Simplicity. Not implementation, architecture acceptance or merge authorization.
**Scope:** `physics_harness/code/`, `libs/` — Python implementation, package entry points and tests.
**Evidence baseline:** [main@2bf977e17](https://github.com/HyungseonSong-plasma/moose-test-repo/commit/2bf977e17fa2e4eb84b24bce51a717bc76be60f7), 2026-11-24.

## 1. Objective and intent

Use the scope census, source-level discriminators, evidence boundaries and KEEP/HOLD alternatives to improve the existing architecture. Reject unnecessary new Git/AST/cache/Graph layers, indiscriminate lazy imports, blanket relocation, file-count targets and new quality scores.

Goal: first make analysis internally accurate, then use the existing Harness to simplify its own implementation. Collect common facts once; keep purpose-specific verification judgments independent.

## 2. Evidence and growth

Reuse [Harness scan #45411795969](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45411795969), attempt 1, request commit `838077fe94efc8eaa1b44bb5c974a6cf11183eb9`, request ID `physical-eV-retirement-impact-20261124`, source revision as above; collectors cpp, moose_input, python_ast, workflow. Request commit is not scanned source. Artifact [#14928832103](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45411795969/artifacts/14928832103), SHA-256 `f91cf4bd3a761b13dfc76a8816595ee323fdc0d08f3f506ebccd5e4dced01bc7`. Checkout, exact-HEAD assertion, scan and upload succeeded. The scan recorded 973 SCANNED / 226 UNRESOLVED; 103,855 nodes, 316,742 edges, 317,941 evidence; 1,896 unresolved entries; zero verification failures; PARTIAL/UNVERIFIED. This is not global consumer closure or semantic equivalence.

Target census: 110 Python files, 91 SCANNED / 19 UNRESOLVED. Baseline `4f873e71f8503943c9fce2dd30fcc96c28d6f631` (2026-11-22, after HU bridge retirement).

| Area | Baseline | Survey baseline | Delta |
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

Python tracked bytes 370,626 → 683,226 (+84.3%); files +69.2%. Verification/tests account for 33/45 additions. Naming implementation: 15 files/159,138 bytes; naming tests: 18 files/123,371 bytes. Growth is descriptive, not a quality verdict.

Preliminary derived figures (892 functions, 125 classes, 1,036 import candidates, 6,676 call candidates, 721 internal import candidates, 278 cross-file edges / 168 non-test edges, 22-module SCC including deferred imports, zero top-level-only SCC) remain preliminary; script/witness set not preserved. Eager initialization and deferred imports must be distinguished; global runtime closure is unproven. Reproduce exact witnesses before using counts as acceptance evidence.

## 3. Architecture and responsibility boundary (KEEP)

| Owner | Responsibility |
|---|---|
| Diagnostics | Exact Git source, AST and external observations; facts and receipts |
| Graph | Canonical identity, nodes, edges, evidence, scope, traversal |
| Analysis | Impact, usage, coverage, interpretation and adapters |
| Libs | Independent Lucidity metric calculation, not decisions |
| Refactor | Alternatives, KEEP/CHANGE, planning |
| Verification | Structure, behavior, consumer, reviewer authority, semantic and replay checks |
| Delete | Existing placeholder; no automatic deletion |
| Tests | Independent positive/negative assertions |

Conceptual fact flow: Diagnostics → Graph → Analysis (uses Libs metric engine) → Refactor → Verification. This is not a new import-layer policy; source-consistency verification remains mandatory during Diagnostics assembly. Retain existing layout, public API, canonical Graph IDs, Lucidity formulas/models and compatibility bridges. No new Framework or common library by default.

## 4. Selected work packages

Paths relative to `physics_harness/code/` unless otherwise indicated. Source anchors are at the pinned survey baseline. All packages are proposals, not implementation permission.

### P1 — AST Symbol Identity

- `diagnostics/providers/python_ast.py:137-141` distinguishes repeated declarations using occurrence; `verification/naming_boundary.py:95-126` can emit repeated keys; `verification/naming_behavior.py:53-64` stores declarations by key (last wins); `verification/naming_semantic_review.py:84-142` uses first matching declaration. A duplicated `def calculate(x)` with different bodies can make reviewers and behavior verification assess different declarations.
- Reuse existing declaration/source extraction primitives in the appropriate owner, without making an AST Framework. Preserve existing canonical IDs and normal unambiguous inputs. For ambiguous legacy Naming keys, fail closed as UNRESOLVED/HOLD rather than select an arbitrary declaration. Explicitly distinguish declaration identity from Python runtime rebinding semantics.
- Preserve decoding, type_comments, scope, nested/async symbols, method/class keys, source locations and signatures. Test duplicate functions/classes/methods, conditional/nested declarations and first/last divergence, invalid encoding/syntax; demonstrate normal-input receipt parity.

### P2 — Git Source Provider responsibility

- `diagnostics/providers/git.py:19-120`, `verification/naming_boundary.py:74-94`, `verification/naming_consumers.py:59-77`, candidate ancestry and other private Git calls repeat tree/read/ancestry mechanics.
- Reuse provider-owned primitives for exact revision inventory, blob verification, historical source and ancestry. Do not collapse HEAD-bound `inventory()` into historical reads or silently alter regular-file filters, error categories, budgets, ordering or stale-SHA handling.
- No `libs/git`. Test exact SHA, missing commit, symlink/submodule, nonregular path, malformed tree, shallow history, changed HEAD, ancestry and byte identity.

### P3 — Naming Verification repeated work

- `verification/naming_gates.py:51-113` calls candidate and behavior; `naming_behavior.py:106-175` calls candidate again; `naming_candidate.py:55-201` invokes boundary; blinded semantic review separately performs baseline KEEP boundary and reads/parses source again.
- Within one trusted invocation, reuse exact source bytes, parsed AST, declaration locations and revision/blob identity where parse options and budgets match. Keep structural, behavior, consumer, semantic and reviewer-authority judgments independent, including baseline KEEP vs candidate-specific judgments.
- No global/persistent cache, untrusted caller-supplied PASS receipts or leakage of candidate names into blind review. Preserve standalone APIs, statuses, blockers, evidence witnesses, truncation and budget semantics. Measure actual Git/AST calls and compare receipts under positives/negatives.

### P4 — Graph Index reuse

- `analysis/usage_matrix.py:166-184` already builds adjacency; `analysis/impact.py:108-201` reconstructs node/evidence/file lookup and scans all edges per target.
- Reuse the existing adjacency and source-scope-bound lookup information inside the multi-target analysis; retain standalone coverage API. No new Graph Query Engine or Graph schema changes.
- For T targets on recorded E=316,742 edges, full edge-pass count approximately (T+1)*E → E plus incident-edge processing. Not a wall-time or memory benchmark. Preserve one-hop semantics, self-reference, ordering, unknown/unscanned surfaces, missing evidence and scope mismatches. Compare all fields of coverage/matrix receipts and measure time/memory on the same graph and targets.

### P5 — Dependency Verification scope

- `verification/dependencies.py:161-165,203-276` checks declared higher-level packages and absolute imports; relative imports and detailed internal module relations are outside current contract. PASS is not proof of internal dependency completeness.
- Reuse existing analyzer and Python AST facts for explicit internal module/relative-import resolution. Distinguish eager top-level, package `__init__` effects, function-local/deferred, and unresolved dynamic imports. Do not turn a preliminary 22-module SCC into an architecture violation.
- Preserve current package-policy results; report additional observed relations separately until explicit approval of any new forbidden-edge policy. Test relative import levels, reexports, module/package ambiguity, deferred imports, genuine eager cycles and unresolved dynamic imports. No second dependency engine.

### P6 — Local implementation and tests

- Preliminary complexity screening: verify_naming_boundary 54 branches, verify_naming_candidate 53, _scan_revision nesting 9. Reproduce metrics before relying on them.
- After P1–P5, simplify remaining functions only where responsibilities become clearer; remove duplicate operations, reduce unnecessary nesting, extract coherent local operations. Do not split files solely because a function is long.
- Reuse repository test fixtures/setup where equivalent; preserve actual Git witnesses, independent assertions, negative controls and exception/validation ordering. Maintain full test coverage obligations.

## 5. Explicit dispositions

| Candidate | Decision | Package / rationale |
|---|---|---|
| Git | ADOPT | P2 |
| Naming repetition | ADOPT | P3 |
| Graph repetition | ADOPT | P4 |
| AST | ADOPT / STRENGTHEN | P1 |
| import coupling | HOLD | Re-evaluate ownership after dependency evidence; no indiscriminate lazy imports |
| complexity | SELECTIVE | P6 |
| tests | SELECTIVE | P6 |
| REST transport | HOLD | Review redirects vs signed archive redirects, credentials, pagination and attempts differ |
| compatibility bridges | HOLD | 10 import-only bridges / 1,632 bytes reported; external/dynamic/serialized consumers unverified |
| Graph model | KEEP | No demonstrated redesign need |
| Lucidity model | KEEP | Existing metric engine |
| dependency scope | ADOPT | P5, no new policy without approval |

Libs: keep `libs/code_lucidity` independent; retain `libs/code_understandability` compatibility bridge and HU/AU/CU calculations. Only simplify demonstrably redundant Analysis adapter conversions with identical outputs; no new aggregate score, new research prerequisite or new library. Direct Lucidity/Planning API measurement remains outstanding.

## 6. Recommended sequence and acceptance

P1 → P5 → P2 → P3 → P4 → P6. P1/P5 correct accuracy and must be independently reviewed, not disguised as behavior-preserving refactors. Other packages are bounded, independently reversible changes; recheck their dependencies and exact main when implementing.

| Gate | Required evidence |
|---|---|
| Baseline | Exact source SHA, reproducible structural witnesses, receipt status/unknowns preserved; baseline Harness tests |
| Identity/API | Normal-input Graph IDs and public interfaces unchanged; deliberate P1/P5 corrections explicitly enumerated |
| Evidence parity | All applicable receipt fields, source refs, ordering, statuses, blockers and budgets compared; no false PASS |
| Model parity | Same Lucidity inputs produce same indicators; no change to formulas or Graph schema |
| Independence | Negative tests, blind review, verifier/reviewer authority and separate judgments preserved |
| Simplification | Actual duplicate operations/implementation reduced; responsibility and code readability examined without forced LOC/file targets |
| Performance | Same Graph/targets, repeatable measurement of calls/time/memory where relevant; theoretical counts not benchmarks |
| Integration | Exact-head existing Harness CI and Repository CI; external/unknown consumer limits retained; separate approval for mutation/merge |

No implementation, test deletion, workflow change, CI weakening or production Physics changes authorized by this proposal. No new Framework, Graph redesign or Lucidity model change.

## 7. Evidence uncertainty

The proposal is based on the existing scan and selected exact-revision source checks. The full Harness was not rerun, full graph derivation/SCC reproduction and external consumer checks are pending, Lucidity and Planning were not directly benchmarked, and no before/after performance or semantic parity is claimed. P1–P6 priorities and sequence are the consolidated design proposal, not accepted results.

**Next gate:** approve the proposed research direction; then separately authorize a bounded implementation/validation package. Keep this PR documentation-only and draft pending review.
