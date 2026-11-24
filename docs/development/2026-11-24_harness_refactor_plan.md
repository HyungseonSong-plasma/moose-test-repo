# Harness Code / Libs — Refactor 계획안

**Status:** RESEARCH / proposal v0.4 — Accuracy, Responsibility & Simplicity. Not implementation, architecture acceptance or merge authorization.
**Scope:** `physics_harness/code/`, `libs/` — Python implementation, package entry points and tests.
**Evidence baseline:** [main@2bf977e17](https://github.com/HyungseonSong-plasma/moose-test-repo/commit/2bf977e17fa2e4eb84b24bce51a717bc76be60f7), 2026-11-24. Current main at preflight: `de51d59d250cac730f24b4a5937c531d27c1e233` (#852), with 17 changed paths outside both source-scope roots. Evidence remains bound to the original SHA; refresh before implementation.

**Evidence authority:** [Survey #2 / PR #855](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/855), pinned [report](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/a817519ca72917d276f80ba3a90ed075ecce8a2a/docs/development/2026-11-24_harness_self_analysis_survey_2.md) and [structured observations](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/a817519ca72917d276f80ba3a90ed075ecce8a2a/docs/development/2026-11-24_harness_self_analysis_survey_2_evidence.json). Survey #1 is preserved at `f5d6cb4`; v0.4 consolidates the reviewed v0.3 proposal with Survey #2 rather than replacing historical evidence.

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

### Survey #2 execution and structural evidence

- [Run #45417660394](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45417660394) and corrected [Run #45417861526](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45417861526) both SUCCESS, exact checkout of the original source. The first run selected call-site nodes for R04/R06; only the corrected declaration metrics are authoritative for these targets. [Artifact #14931164970](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45417861526/artifacts/14931164970), ZIP SHA-256 `9d259ca5b4f8c1342a1357f00a5ba1b72fe2e4579430ab85dd4241be99ebf932`, hash verified in Survey #2. Durable JSON contains log-derived observations, not an identical artifact copy. The branch-only workflow was removed; the exact executed script remains in history.
- Scoped python_ast scan: 110 files (91 SCANNED / 19 UNRESOLVED), 11,847 nodes / 34,208 edges / 34,318 evidence, 94 unresolved entries, zero verification failures, PARTIAL/UNVERIFIED. Full repository and scoped counts are not interchangeable.
- Actual Lucidity and Planning API evaluation: eight KEEP/CHANGE pairs HOLD/HOLD at full survey scope; seven individual files COMPLETE/VERIFIED and both alternatives ADMISSIBLE, no recommendation; run_scan still PARTIAL/UNVERIFIED and HOLD/HOLD. Neither ADMISSIBLE nor VERIFIED proves behavior or improvement. _symbol_inventory: 31 LOC, 6 branches, depth 6; _scan_revision: 67 LOC, 22 branches, depth 9; run_scan: 197 LOC, 36 branches, depth 4; derive_indicators: 38 LOC, 4 branches, depth 2. These are source-derived traits, not a human comprehension score.
- Prior broad-Graph static derivation: 721 internal import candidates, 278 distinct non-self cross-file pairs, 168 non-test pairs. SCC: one 22-file group with all candidate relations, two groups (7 and 2) after excluding package __init__ endpoints, none under column-zero-only proxy. This is not runtime import resolution; exact edge witness list and executable derivation must be preserved before making this a new acceptance gate. Seven-module collector/assembler/receipt/provider composition coupling and two-module naming/provenance coupling are distinct; no demand to eliminate SCCs.
- Exact tracked-repository git grep and bounded owner-indexed search completed (Survey #2 section 6). Eight legacy paths remain HOLD; two documented stable lucidity adapter paths KEEP. No global external/dynamic/serialized consumer closure.
- R04 duplicate-declaration source binding defect reproduced twice with unique declaration negative control; see P1. R03 baseline timing measured twice; see P4. Other candidate benefits remain hypotheses.

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

## 4. Selected work packages (proposal only)

Paths below are relative to `physics_harness/code/`. Source anchors refer to the original survey SHA. ADOPT means a recommended design direction, not permission to edit. Each package has a KEEP alternative, bounded scope, explicit discriminator and independent acceptance. No new framework, layout or model change by default.

### P1 — AST Symbol Identity (ADOPT, first; correctness repair, not pure refactor)

**Observed defect (R04/S02):** `diagnostics/providers/python_ast.py:137-141` distinguishes repeated declarations; `verification/naming_boundary.py:95-126,225` emits duplicate keys and indexes last declaration; `naming_behavior.py:53-64` also selects last; `naming_semantic_review.py:100-142` selects first. Actual immutable Git fixture: `def transform(x): return x + 1` at line 1 and `def transform(x): return x - 1` at line 4. Boundary returns STRUCTURE_WITNESSED and packet has no unresolved entries, but its line-4 reference carries line-1 code; behavior selector selects line 4. Duplicate blob `b4298735b38d0b804cbbc5cd2d2edc19f6a54347`; unique control `73bca47390c4e0c82369c06ecaad4ae2dc427a4f` returns matching code. Both executions reproduce. This is a source-evidence defect, not proof of current Harness runtime incompatibility.

**Alternatives:** KEEP leaves defect; full AST unification overreaches; preferred minimal repair validates exact declaration anchors and fails closed on ambiguous legacy Naming keys. Use existing occurrence identity or exact source position where compatible; no new global Symbol ID model. A local common declaration lookup is justified only if consumers share its semantics. Do not equate declaration identity with Python runtime rebinding.

**Bounded scope:** naming_boundary, naming_behavior, naming_semantic_review, candidate/gates only where propagation is necessary, focused tests. Diagnostics canonical IDs remain unchanged. Preserve each consumer's supported syntax, decoding and type_comments behavior; do not silently broaden unsupported nested/conditional declarations. Normal overloads and property getter/setter are not automatically invalid Python; distinguish declarations or explicitly HOLD when a legacy key cannot disambiguate them.

**Acceptance:**
- Reproduce old mismatch on baseline; corrected line-4 excerpt must match line-4 immutable blob declaration, or emit explicit ambiguity and omit the untrustworthy excerpt. No STRUCTURE_WITNESSED on ambiguous binding; no behavior match derived from arbitrary first/last; gate cannot promote unresolved evidence.
- Unique declarations: same normal keys, source refs, signatures, executable body projections, receipt fields, exception/budget behavior. Graph IDs unchanged. Compare semantic receipt fields after normalizing only legitimate revision-dependent metadata; never compare different HEADs as if identical.
- Negative/control matrix: duplicate functions/classes/methods, overloads, getter/setter, nested/conditional declarations, async, signature and encoding/syntax errors; exact anchor and excerpt match, tampered blob/location rejected or HOLD. Exercise public Boundary, candidate/behavior and blinded packet/gate integration, not only private AST helpers.
- Review explicit intended status changes independently of any later deduplication. No semantic PASS claim.

### P2 — Git Source Provider responsibility (ADOPT, minimal internal seam)

**Observed (R01):** `diagnostics/providers/git.py:19-120` already owns assert_head, inventory, read and read_at_revision. Boundary and consumer inventory helpers (`verification/naming_boundary.py:74-94`, `naming_consumers.py:59-77`) duplicate tree traversal; other modules use private _git for commit/ancestry.

**Alternatives:** KEEP repeated Git mechanics vs reuse existing provider primitives. Prefer extracting common internal tree-row reading and immutable revision validation first; add narrow public methods only if real consumers need them. No separate Git library or raw command exposure. Provider obtains authenticated Git facts, consumers select regular Python/text paths and own domain-specific errors and budgets. HEAD-bound inventory must stay distinct from historical reads.

**Acceptance:** exact SHA/blob/size, deterministic ordering, HEAD mismatch, historical commit absent, invalid object, malformed tree, symlink/submodule/nonregular path and shallow history fixtures. Ancestry must distinguish proved ancestor, proved non-ancestor and unproven/unavailable history; no boolean collapse of unknown into false or true. Preserve existing callers' error categories/fail-closed dispositions unless an explicitly reviewed correctness correction requires a change. Compare selected inventories and source bytes; measure actual duplicate Git calls before and after. Stop if abstraction adds public complexity without reducing genuine duplicate mechanics. P2 can be designed independently of P1; serialize overlapping edits.

### P3 — Naming repeated observations (conditional ADOPT after P1/P2)

**Observed (R02):** `verification/naming_gates.py:51-113` calls candidate and behavior; behavior calls candidate again; candidate calls boundary; blinded review calls boundary using a separate KEEP option and reparses source. Some redundancy defends against untrusted receipts.

**Alternatives:** KEEP if duplicate work is small; global cache/receipt reuse rejected; prefer existing orchestrator with one internal execution-lifetime observation reuse seam. Start by eliminating duplicate source reads within a single boundary call. Then instrument full gate and compare a minimal internal reuse path. Existing standalone APIs remain independently verifying, no caller-managed cache or caller-provided PASS. Share verified immutable observations only (repository, revision, path, blob, parser options and applicable budget); do not share candidate-specific judgments or leak names into blinded review. Budget checks must still run per intended consumer even on reuse; no mutable AST cross-consumer side effects.

**Acceptance:** baseline and candidate call counts for Git reads and AST parses, same fixtures/options, receipt field parity across KEEP, EXTRACT/RENAME, unresolved and error cases; preserve source and option identity, separate independent judgments, reviewer authority, truncation and fail-closed semantics. Explicitly show P1 ambiguity repair remains effective. If repeated work cannot be safely reduced without changing APIs or independent contracts, KEEP.

### P4 — Graph index reuse (CONDITIONAL, medium priority)

**Observed (R03):** `analysis/usage_matrix.py:166-184` creates adjacency while `analysis/impact.py:108-201` rebuilds indexes and scans edges per target. Scoped actual baseline, 34,208 edges, 3 repetitions per target count, same deterministic non-test targets, CALLS_CANDIDATE FORWARD, DEFINES ignored:

| Targets | Run 1 median ms | Run 2 median ms |
|---:|---:|---:|
| 1 | 19.4 | 22.7 |
| 10 | 71.6 | 77.4 |
| 50 | 310.1 | 326.7 |

Scaling exists but local absolute cost is modest. Broad 316,742-edge graph pass count is a theoretical (T+1)*E, not a measured runtime. No optimized speedup demonstrated.

**Alternatives:** KEEP for ordinary workloads; prefer reusing existing batch adjacency in private coverage logic if small and direct. Do not introduce Graph Query Engine, persistent indexes, Graph model state or user-managed index. Extend to Lucidity/Planning only if their measured workload justifies it.

**Acceptance / stop rule:** reproduce same workloads and representative larger usage (if relevant), report elapsed time, peak memory and traversal counts under repeated identical conditions; verify entire rows and receipts, scope mismatch, ordering, one-hop, missing and unresolved surfaces, ignored/unclassified edges, runtime cross-HEAD and self-reference. Proceed only if a repeatable benefit or clearly reduced repeated work is shown without disproportionate memory/API/maintenance cost. Record workload/threshold rationale before implementation; no invented universal speed threshold. Otherwise KEEP. P4 is independent of P3.

### P5 — Dependency observation and policy boundary (RESEARCH; not implementation ADOPT)

**Observed (R05/R12):** existing contract in `ci/contracts/harness_dependencies.json` targets outer packages; `verification/dependencies.py:161-165,203-276` checks absolute imports against declared policy, not Code-internal relative/dynamic closure. This is an explicit coverage gap, not proof of incorrect existing PASS. Static 22/7+2/0 SCC counts do not mandate new violations. `diagnostics/assemble.py:158` requires source consistency; package __init__ loads unrelated verification modules. A submodule import alone does not bypass Python package initialization.

**Ownership hypothesis:** Diagnostics collects source import observations and resolution candidates; Graph preserves facts/evidence; Analysis derives scoped dependency relationships/SCCs; Verification evaluates explicit DependencyContract. Check existing graph/provider consumers and available import facts before deciding where minimal resolution belongs. Existing naming/provenance and collector composition relationships may be legitimate. No blanket lazy imports or physical relocation.

**Research exit gate:** document existing vs needed import facts, representative relative levels, reexports, ambiguous modules, eager/deferred and conditional imports, dynamic uncertainty, actual package initialization and source-consistency independence. Compare KEEP vs narrow observation/reporting addition; retain separate old policy results. A new forbidden-edge/CI contract, dependency engine, owner relocation or API change requires separate approval. No dependency on P5 for P1/P2/P3 unless new evidence shows one.

### P6 — Local implementation and tests (SELECTIVE)

Use actual declaration metrics as screening, not a quality threshold. _scan_revision depth 9 and _symbol_inventory depth 6 justify individual inspection; run_scan is a negative control (length alone insufficient). Prefer local guard clauses, linear flow, and coherent named operations only where they clarify actual responsibility. Recheck after relevant earlier work; independent local changes need not wait for unrelated P4/P5. Reuse existing git_factory where equivalent. Preserve tests' independent assertions, Git witnesses and validation/error order. No test deletion, generic fixture framework, file-count target or automatic extraction.

**Acceptance:** candidate-specific before/after source and receipt evidence; unchanged tests plus targeted negative controls, exact revision replay; reduced actual duplication or clearer responsibilities/call paths, not simply fewer lines. KEEP if no demonstrated benefit.

## 5. Explicit dispositions

| Candidate | Decision | Package / rationale |
|---|---|---|
| R04 AST identity | ADOPT FIRST | P1 reproduced correctness repair |
| R01 Git | ADOPT MINIMAL | P2 provider ownership, preserve contracts |
| R02 Naming repetition | CONDITIONAL ADOPT | P3 after P1/P2, measured safe reuse |
| R03 Graph repetition | CONDITIONAL | P4 small current latency; no generic cache |
| R05 import coupling | RESEARCH/HOLD | P5 ownership review; no lazy-import expansion |
| R06 complexity | SELECTIVE | P6 |
| R07 tests | SELECTIVE | P6 |
| R08 REST transport | HOLD | Redirect/credentials/attempt/security contracts differ |
| R09 compatibility | HOLD / KEEP | Eight legacy paths HOLD; two documented stable APIs KEEP |
| R10 Graph model | KEEP | No redesign evidence |
| R11 Lucidity | KEEP | Preserve independent formulas/models and public API |
| R12 dependency scope | RESEARCH | P5 observation/policy boundary; no CI change |

Libs: `libs/code_lucidity` is a KEEP baseline (actual derive_indicators evaluation, independent numerical model). No formula or metric change. Internal implementation only if concrete duplication is independently demonstrated; Analysis adapter conversion only if equivalent output and consumers justify it. `libs/code_understandability` bridge HOLD; documented stable Analysis adapter paths KEEP. No new aggregate score, new model or library. Actual Lucidity indicators do not measure semantic cohesion or human comprehension.

## 6. Execution dependencies and acceptance

```text
Approve bounded implementation scope (not this document edit)
  P1 (first correctness repair) ----+
  P2 (independent design; serialize overlapping edits) --+--> P3 conditional design/reuse
  P4 (independent; workload/benefit gate)
  P5 (independent research only; separate policy/implementation approval)
  P6 (selective, after relevant changes; not a mandatory final sweep)
```

Recommended first implementation candidate: P1, after exact-head baseline and explicit approval. P2 separately; P3 depends on verified P1 identity and P2 acquisition contracts. P4/P5 are independent options, not gates on all other work. P6 is local and justified by remaining evidence. No forced execution of all packages. Design decisions remain proposals; user approves package scope separately.

| Gate | Required evidence |
|---|---|
| Baseline | Refresh exact main, inspect changed scope and dependencies, reproduce exact target witnesses and run baseline Harness tests. Keep broad/narrow unknowns separate |
| Identity/API | Normal-input Graph IDs/public interfaces preserved; explicitly enumerate intended P1 correctness deltas; no silent changes in error or budget behavior |
| Evidence parity | Compare all applicable semantic receipt fields and ordering with documented normalization of revision-bound IDs/metadata; preserve unresolved and blockers; no false PASS |
| Model parity | Identical Lucidity input facts yield identical indicators, no Graph schema/formula change |
| Independence | Negative controls, blind review, verifier/reviewer authority and purpose-specific judgments preserved |
| Simplicity | Compare KEEP vs candidate; show reduced actual operations or clearer responsibilities without new user-facing concepts; avoid forced LOC targets |
| Performance | P2/P3 operation counts and P4 repeated time/memory/traversals, same workload; no theoretical speedup claim |
| Integration | Existing exact-head Harness CI and Repository CI; independently review intended corrections and impacted tests; retain external/unknown limits |
| Rollback | Separate bounded package/PR, no unrelated edits; explicit revert path, recheck dependent packages |
| Authorization | Implementation and merge separately approved; research completion or ADMISSIBLE is not mutation permission |

## 7. Review response and remaining uncertainty

| Finding | v0.4 response |
|---|---|
| F01 stale evidence | Section 2 integrates Survey #2 actual runs, timing, API evaluation and bounded consumer search |
| F02 P1 | Explicit anchor/excerpt invariant, ambiguity HOLD and public gate controls |
| F03 P5 | Observation vs analysis vs policy ownership; research-only decision |
| F04 P3 | Orchestrator-private reuse, per-consumer budgets and independent judgments; P1/P2 prerequisites |
| F05 P4 | Actual modest latency, conditional benefit gate, KEEP option |
| F06 sequencing / Git | Independent work graph and precise Git contract, no mandatory serial chain |
| F07 Libs | KEEP model, HOLD legacy, selective internal work only on evidence |

Survey #2 ran the existing Harness and directly evaluated Lucidity/Planning, reproduced the duplicate declaration bug, measured baseline Usage Matrix timing, and performed bounded consumer search. No candidate implementation, full pytest replay, before/after parity, optimized performance, global consumer closure or measured human comprehension has been established. Static SCC derivation is not canonical runtime resolution. Confirm exact source and dependency state before starting a package. No implementation, test deletion, workflow/CI policy change, physics changes, merge or architecture acceptance authorized by this document.

**Next gate:** review v0.4, then separately authorize a bounded P1 implementation/validation package. Keep this PR documentation-only and draft. Survey #2 remains a separate evidence PR.
