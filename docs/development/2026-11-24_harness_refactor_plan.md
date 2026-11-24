# Harness Code / Libs — Refactor 계획안

**Status:** RESEARCH / proposal v0.5 — Accuracy, Responsibility & Simplicity. Not implementation, architecture acceptance or merge authorization.
**Scope:** `physics_harness/code/`, `libs/` — Python implementation, package entry points and tests.
**Evidence baseline:** [main@2bf977e17](https://github.com/HyungseonSong-plasma/moose-test-repo/commit/2bf977e17fa2e4eb84b24bce51a717bc76be60f7), 2026-11-24. Current main rechecked at v0.5 preflight: `de51d59d250cac730f24b4a5937c531d27c1e233` (#852), with 17 changed paths outside both source-scope roots. Evidence remains bound to the original SHA; refresh before implementation.

**Evidence authority:** [Survey #2 / PR #855](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/855), pinned [report](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/a817519ca72917d276f80ba3a90ed075ecce8a2a/docs/development/2026-11-24_harness_self_analysis_survey_2.md) and [structured observations](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/a817519ca72917d276f80ba3a90ed075ecce8a2a/docs/development/2026-11-24_harness_self_analysis_survey_2_evidence.json).

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

- [Run #45417660394](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45417660394) and corrected [Run #45417861526](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45417861526) both SUCCESS, exact checkout of the original source. The first run selected call-site nodes for R04/R06; only the corrected declaration metrics are authoritative for these targets. [Artifact #14931164970](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45417861526/artifacts/14931164970), ZIP SHA-256 `9d259ca5b4f8c1342a1357f00a5ba1b72fe2e4579430ab85dd4241be99ebf932`, hash verified in Survey #2. Durable JSON contains log-derived observations, not an identical artifact copy. The branch-only execution workflow was removed.
- Scoped python_ast scan: 110 files (91 SCANNED / 19 UNRESOLVED), 11,847 nodes / 34,208 edges / 34,318 evidence, 94 unresolved entries, zero verification failures, PARTIAL/UNVERIFIED. Full repository and scoped counts are not interchangeable.
- Actual Lucidity and Planning API evaluation: eight KEEP/CHANGE pairs HOLD/HOLD at full survey scope; seven individual files COMPLETE/VERIFIED and both alternatives ADMISSIBLE, no recommendation; run_scan still PARTIAL/UNVERIFIED and HOLD/HOLD. Neither ADMISSIBLE nor VERIFIED proves behavior or improvement. _symbol_inventory: 31 LOC, 6 branches, depth 6; _scan_revision: 67 LOC, 22 branches, depth 9; run_scan: 197 LOC, 36 branches, depth 4; derive_indicators: 38 LOC, 4 branches, depth 2. These are source-derived traits, not a human comprehension score.
- Broad-Graph static derivation: 721 internal import candidates, 278 distinct non-self cross-file pairs, 168 non-test pairs. SCC: one 22-file group with all candidate relations, two groups (7 and 2) after excluding package __init__ endpoints, none under column-zero-only proxy. This is not runtime import resolution; exact edge witness list and executable derivation must be preserved before making this a new acceptance gate. Seven-module collector/assembler/receipt/provider composition coupling and two-module naming/provenance coupling are distinct; no demand to eliminate SCCs.
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

**Observed defect (R04/S02):** `diagnostics/providers/python_ast.py:137-141` distinguishes repeated declarations; `verification/naming_boundary.py:95-126,225` emits duplicate keys and indexes last declaration; `naming_behavior.py:53-64` also selects last; `naming_semantic_review.py:100-142` selects first. Actual immutable Git fixture: `def transform(x): return x + 1` at line 1 and `def transform(x): return x - 1` at line 4. Boundary returns STRUCTURE_WITNESSED and packet has no unresolved entries, but its line-4 reference carries line-1 code; behavior selector selects line 4. Duplicate blob `b4298735b38d0b804cbbc5cd2d2edc19f6a54347`; unique control `73bca47390c4e0c82369c06ecaad4ae2dc427a4f` returns matching code. Both runs reproduce. **Additional source-derived risk:** `naming_candidate.py:138-153` builds key_set and after_symbols dicts from observed declarations, overwriting duplicate keys; candidate owner and extraction destinations enter after_paths. This is confirmed from code at current main, but the new candidate/destination counterexamples have not yet been run.

**Selected first design:** keep existing public Naming keys and canonical Graph IDs. Collect declarations without overwriting collisions before selecting a target. Ambiguous relevant legacy keys must fail closed as HOLD with explicit source-bound reasons (REJECTED only for actual contradiction); a diagnostic inventory may retain all ambiguous observations but may not claim a validated binding, placement, comparison or review excerpt for them. Do not add public occurrence IDs, change key formats or unify AST engines in P1. More expressive occurrence identity is a separately approved design only if later justified. No claim that duplicate declarations, overloads or property accessors are Python errors; declaration identity is not runtime rebinding.

**Invariant:** any accepted binding, before/after placement, signature, body projection or blinded excerpt refers to exactly one declaration in the corresponding immutable repository/revision/path/blob, matching its declaration anchor and owner. Do not choose first/last merely by order or match on body/signature alone. Check anchor, declaration kind, owner and actual source region before emitting evidence. Preserve each consumer's parsing options (including behavior type_comments=True), decoding, truncation and budgets. No silent broadening to unsupported nested or conditional binding.

| Selected scope | Ambiguity policy |
|---|---|
| FILE / FOLDER | All supported declarations in selected file(s); any duplicate relevant owner/key or conflicting binding prevents complete witnessed result. Existing folder candidate limitations remain HOLD |
| CLASS | Selected class and its methods. Duplicate parent class makes its dependent method identity ambiguous even when each method name occurs once; no cross-class merging |
| FUNCTION | Selected top-level function key. Duplicate unrelated names outside selected target/bindings/placement scope do not alone cause HOLD |
| Candidate / extraction | Check both baseline and candidate mapped owner scope, every before/after placement and affected extraction destination owner scope. For full-file ownership, all supported declarations in that file are relevant; for a bounded class/function placement, include selected declarations and enclosing owner identity. Detect collisions in destination inventories before dict projection. Do not allow unrelated ambiguity to clear or incorrectly block a unique scoped target |
| Unsupported nested/conditional | No new binding support. When requested identity or relevant owner cannot be uniquely established under current supported inventory (including competing conditional declarations), disclose unresolved/HOLD; do not infer runtime rebinding or expand to whole-program analysis |

**Bounded P1 change envelope (proposal; confirm at approval):** `verification/naming_boundary.py`, `verification/naming_candidate.py`, `verification/naming_behavior.py`, `verification/naming_semantic_review.py`; `verification/naming_gates.py` only if needed to propagate the explicit issue. Candidate is mandatory in scope, not optional. Existing tests `tests/test_naming_boundary.py`, `test_naming_candidate.py`, `test_naming_behavior.py`, `test_naming_semantic_review.py`, `test_naming_gates.py`; existing repository boundary/semantic tests may be extended only for exact anchor controls. No change to Git provider, DependencyContract, Graph, Libs, public receipt fields, CI or layout. Any scope expansion requires renewed approval.

**Mandatory acceptance matrix (execute on exact before/after fixtures):**

| Case | Required result |
|---|---|
| Unique → unique, valid rename/extraction and unique destination | Preserve existing binding/placement/comparison/excerpt and status contracts; no new ambiguity flag |
| Unique → duplicate | Candidate relevant key unresolved; no validated_placements for ambiguous pair; no arbitrary comparison |
| Duplicate → unique | Baseline ambiguous; after uniqueness cannot retroactively authenticate before evidence |
| Duplicate → duplicate, reordered or changed bodies | No successful placement/comparison from first/last or signature coincidence |
| Existing/new extraction destination duplicate | No validated destination placement on ambiguous relevant owner/key |
| Duplicate class, same/different method names | No cross-class method identity or merged owner; parent ambiguity propagates |
| Overload/property accessor, nested/conditional, async, malformed encoding/syntax | Supported unique declarations preserve behavior; ambiguous or unsupported relevant identity explicitly HOLD, not Python-invalid solely for repetition |
| Unrelated duplicate for unique class/function target | No blanket file-level rejection; existing unrelated uncertainties preserved |
| Anchor/blob contradiction, truncated excerpts, budget limits | Exact anchor-to-code match for accepted excerpt; omit ambiguous or wrong excerpt, retain explicit failures/unknowns and budget behavior |

Run baseline public Boundary/Candidate/Behavior/Blind/Gate cases, including original mismatch and candidate-side cases to establish expected failure before changes. Assert internal receipt fields (`observed_symbols` as observations, binding witnesses, `validated_placements`, `comparisons`, excerpt refs and content, blockers/unresolved), not just final HOLD (gate is already bounded BLOCKED/HOLD). No STRUCTURE_WITNESSED or STRUCTURAL_DELTA_VERIFIED on relevant ambiguity. No behavioral success or review evidence based on an arbitrary declaration. Independently verify normal receipt parity, preserving legitimate revision-bound metadata with documented normalization only. Run existing Harness tests and exact-head CI after a bounded edit; separately review intended status changes. Correctness repair may increase LOC if needed; no deduplication target. STOP on unsupported scope, identity uncertainty, or unexplained normal-input regressions; revert the bounded P1 commit/PR if acceptance fails.

### P2 — Git Source Provider responsibility (ADOPT, minimal internal seam)

**Observed (R01):** `diagnostics/providers/git.py:19-120` already owns assert_head, inventory, read and read_at_revision. Boundary and consumer inventory helpers (`verification/naming_boundary.py:74-94`, `naming_consumers.py:59-77`) duplicate tree traversal; other modules use private _git for commit/ancestry.

**Alternatives:** KEEP repeated Git mechanics vs reuse existing provider primitives. Prefer extracting common internal tree-row reading and immutable revision validation first; add narrow public methods only when an actual need shared by multiple consumers is demonstrated; first change only tree-row parsing and immutable Git facts. Do not move file selection, budgets, validation policies or domain receipt/error decisions into the provider. No separate Git library or raw command exposure. Provider obtains authenticated Git facts, consumers select regular Python/text paths and own domain-specific errors and budgets. HEAD-bound inventory must stay distinct from historical reads.

**Acceptance:** exact SHA/blob/size, deterministic ordering, HEAD mismatch, historical commit absent, invalid object, malformed tree, symlink/submodule/nonregular path and shallow history fixtures. Ancestry contract: proved ancestor; proved non-ancestor only with sufficient history; unproven for missing objects, shallow boundary, timeout or execution errors. Exit 1 alone is insufficient if history is shallow or incomplete. Current _git maps every nonzero to ValueError, and naming_candidate maps that to CANDIDATE_NOT_DESCENDANT_OF_BASELINE. Test true ancestry, unrelated commits with sufficient history, shallow missing history and execution failure. Ancestry UNKNOWN must reach consumer unresolved/HOLD rather than a false non-descendant verdict. Correcting existing misclassification is a separately approved intended delta, not pure dedup parity; keep it outside initial tree-row change. Preserve existing callers' error categories/fail-closed dispositions unless an explicitly reviewed correctness correction requires a change. Compare selected inventories and source bytes; measure actual duplicate Git calls before and after. Stop if abstraction adds public complexity without reducing genuine duplicate mechanics. P2 can be designed independently of P1; serialize overlapping edits.

### P3 — Naming repeated observations (conditional ADOPT after P1/P2)

**Observed (R02):** `verification/naming_gates.py:51-113` calls candidate and behavior; behavior calls candidate again; candidate calls boundary; blinded review calls boundary using a separate KEEP option and reparses source. Some redundancy defends against untrusted receipts.

**Alternatives:** KEEP if duplicate work is small; global cache/receipt reuse rejected; prefer simple call structure in three ordered steps: (1) remove repeated source read within a single Boundary invocation after P1; (2) instrument and simplify demonstrably redundant internal calls where independent judgments and budgets are unchanged; (3) only if measured residual repetition warrants it, consider orchestrator-private execution-lifetime observation reuse. Cache is not the objective. P1 must be stable for step 1; P2 contract must be verified before cross-consumer acquisition reuse, not a prerequisite for measuring step 1. Existing standalone APIs remain independently verifying, no caller-managed cache or caller-provided PASS. Share verified immutable observations only (repository, revision, path, blob); when parse options, scope, error order or budget differ, reuse bytes only if safe, not AST or judgment; do not share candidate-specific judgments or leak names into blinded review. Budget checks must still run per intended consumer even on reuse; no mutable AST cross-consumer side effects.

**Acceptance:** baseline and candidate call counts for Git reads and AST parses, same fixtures/options, receipt field parity across KEEP, EXTRACT/RENAME, budget overflow, tampered evidence, unresolved and error cases, plus independent standalone calls; preserve source and option identity, separate independent judgments, reviewer authority, truncation and fail-closed semantics. Explicitly show P1 ambiguity repair remains effective. If repeated work cannot be safely reduced without changing APIs or independent contracts, KEEP.

### P4 — Graph index reuse (CONDITIONAL, low priority)

**Observed (R03):** `analysis/usage_matrix.py:166-184` creates adjacency while `analysis/impact.py:108-201` rebuilds indexes and scans edges per target. Scoped actual baseline, 34,208 edges, 3 repetitions per target count, same deterministic non-test targets, CALLS_CANDIDATE FORWARD, DEFINES ignored:

| Targets | Run 1 median ms | Run 2 median ms |
|---:|---:|---:|
| 1 | 19.4 | 22.7 |
| 10 | 71.6 | 77.4 |
| 50 | 310.1 | 326.7 |

Scaling exists but local absolute cost is modest. Broad 316,742-edge graph pass count is a theoretical (T+1)*E, not a measured runtime. No optimized speedup demonstrated.

**Alternatives:** KEEP for ordinary workloads; prefer reusing existing batch adjacency in private coverage logic if small and direct. Do not introduce Graph Query Engine, persistent indexes, Graph model state or user-managed index. Extend to Lucidity/Planning only if their measured workload justifies it.

**Acceptance / stop rule:** before approval freeze Graph source/scope, ordered target IDs, selectors, known workload, measurement environment, repetitions (at least three paired repeats per 1/10/50-target baseline/candidate, same warm/cold protocol; add representative larger workload only when justified) and benefit/memory criterion. Report elapsed time, peak memory and traversal counts; verify entire rows and receipts, scope mismatch, ordering, one-hop, missing and unresolved surfaces, ignored/unclassified edges, runtime cross-HEAD and self-reference. Proceed only if existing adjacency reuse also makes the code simpler and reduces actual repeated work with a repeatable, relevant benefit and no disproportionate memory/API/maintenance cost. If separate optimization infrastructure is necessary, KEEP. Record workload/threshold rationale before implementation; no invented universal speed threshold. Otherwise KEEP. P4 is independent of P3.

### P5 — Dependency observation and policy boundary (RESEARCH; not implementation ADOPT)

**Observed (R05/R12):** existing contract in `ci/contracts/harness_dependencies.json` targets outer packages; `verification/dependencies.py:161-165,203-276` checks absolute imports against declared policy, not Code-internal relative/dynamic closure. This is an explicit coverage gap, not proof of incorrect existing PASS. Static 22/7+2/0 SCC counts do not mandate new violations. `diagnostics/assemble.py:158` requires source consistency; package __init__ loads unrelated verification modules. A submodule import alone does not bypass Python package initialization.

**Ownership hypothesis:** Diagnostics collects source import observations and resolution candidates; Graph preserves facts/evidence; Analysis derives scoped dependency relationships/SCCs; Verification evaluates explicit DependencyContract. Check existing graph/provider consumers and available import facts before deciding where minimal resolution belongs. Existing naming/provenance and collector composition relationships may be legitimate. No blanket lazy imports or physical relocation.

**Research entry:** classify the scoped scan's 19 UNRESOLVED files and 94 unresolved entries against the exact receipt/Graph and source anchors, without conflating file counts with entry counts. Categorize analyzer defect, unsupported capability/scope, dynamic reference, or inherent static limitation; retain legitimate UNKNOWN, identify counterexamples for actual defects, and record unclassified entries explicitly. These counts are observed; classification is a future P5 research deliverable, not completed here. Establish which dependency questions existing observations already answer and which actually need more evidence. No default expansion of CI or new engine.

**Research exit gate:** document existing vs needed import facts, representative relative levels, reexports, ambiguous modules, eager/deferred and conditional imports, dynamic uncertainty, actual package initialization and source-consistency independence. Compare KEEP vs narrow observation/reporting addition; retain separate old policy results. A new forbidden-edge/CI contract, dependency engine, owner relocation or API change requires separate approval. Exit with KEEP/no work if existing observations answer required questions or additional observations lack demonstrated need. SCC count is a diagnostic, not grounds for policy changes. No dependency on P5 for P1/P2/P3 unless new evidence shows one.

### P6 — Local implementation and tests (SELECTIVE)

Use actual declaration metrics as screening, not a quality threshold. _scan_revision depth 9 and _symbol_inventory depth 6 justify individual inspection; run_scan is a negative control (length alone insufficient). Prefer local guard clauses, linear flow, and coherent named operations only where they clarify actual responsibility. Recheck after relevant earlier work; independent local changes need not wait for unrelated P4/P5. Reuse existing git_factory where equivalent. Preserve tests' independent assertions, Git witnesses and validation/error order. No test deletion, generic fixture framework, file-count target or automatic extraction.

**Acceptance:** candidate-specific before/after source and receipt evidence; unchanged tests plus targeted negative controls, exact revision replay; show before/after understanding path for one function or test (entry point, relevant decisions, data owner, assertions), reduced actual duplication or clearer responsibilities/call paths, not simply fewer lines. KEEP/no work if no demonstrated benefit, including Libs.

## 5. Explicit dispositions

| Candidate | Decision | Package / rationale |
|---|---|---|
| R04 AST identity | ADOPT FIRST | P1 reproduced correctness repair |
| R01 Git | ADOPT MINIMAL | P2 provider ownership, preserve contracts |
| R02 Naming repetition | CONDITIONAL ADOPT | P3 after P1, P2 contract for cross-consumer reuse; measured safe simplification |
| R03 Graph repetition | CONDITIONAL | P4 low priority, modest latency; no generic cache |
| R05 import coupling | RESEARCH/HOLD | P5 ownership review; no lazy-import expansion |
| R06 complexity | SELECTIVE | P6 |
| R07 tests | SELECTIVE | P6 |
| R08 REST transport | HOLD | Redirect/credentials/attempt/security contracts differ |
| R09 compatibility | HOLD / KEEP | Eight legacy paths HOLD; two documented stable APIs KEEP |
| R10 Graph model | KEEP | No redesign evidence |
| R11 Lucidity | KEEP | Preserve independent formulas/models and public API |
| R12 dependency scope | RESEARCH | P5 classify unresolved and observation/policy boundary; no CI change |

Libs: `libs/code_lucidity` is a KEEP baseline (actual derive_indicators evaluation, independent numerical model). No formula or metric change. Internal implementation only if concrete duplication is independently demonstrated; Analysis adapter conversion only if equivalent output and consumers justify it. `libs/code_understandability` bridge HOLD; documented stable Analysis adapter paths KEEP. No new aggregate score, new model or library. Actual Lucidity indicators do not measure semantic cohesion or human comprehension.

## 6. Execution dependencies and acceptance

```text
Approve bounded implementation scope (not this document edit)
  P1 (first correctness repair) ----+
  P2 (independent design; serialize overlapping edits) --+--> P3 cross-consumer reuse
  P3 local read simplification (after P1; no P2 dependency)
  P4 (independent; workload/benefit gate)
  P5 (independent research only; separate policy/implementation approval)
  P6 (selective, after relevant changes; not a mandatory final sweep)
```

Recommended first implementation candidate: P1, after exact-head baseline and explicit approval. P2 separately; P3 begins with a local repeated-read candidate after P1; cross-consumer reuse additionally depends on verified P2 acquisition contracts. P4/P5 are independent options, not gates on all other work. P6 is local and justified by remaining evidence. No forced execution of all packages. Design decisions remain proposals; user approves package scope separately.

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

## 7. Package entry/exit contracts and remaining uncertainty

Before approving any package, freeze a short package-specific contract: exact main SHA and actual impacted paths, allowed changed files, preserved API/receipt, intended deltas, mandatory tests, measurement if applicable, rollback point and STOP/KEEP conditions. The P1 envelope and test matrix above are the proposed first contract; no package is approved by this plan. P2–P6 contracts are frozen only when individually selected, not speculative new work.

| Package | Completion / STOP |
|---|---|
| P1 | Correct evidence binding and explicit ambiguity across all public gates; correctness may increase LOC; no normal-input regression |
| P2 | Demonstrate eliminated duplicate tree mechanics and unchanged consumer contracts; stop on unnecessary API growth; ancestry correction separately approved |
| P3 | Demonstrate removed actual reads/calls, preserve independent judgments; stop if reuse changes evidence/budget/error behavior |
| P4 | Demonstrate relevant measured work reduction and simpler existing code at same semantics; KEEP if benefit too small or separate optimization layer needed |
| P5 | Classify unresolved evidence, answer scoped dependency questions with existing facts where sufficient; KEEP legitimate UNKNOWN; separate approval for any change |
| P6 / Libs | One local before/after understanding path, independent test evidence; explicitly KEEP/no work if no justified change |

Survey #2 ran the existing Harness and directly evaluated Lucidity/Planning, reproduced the duplicate declaration bug, measured baseline Usage Matrix timing, and performed bounded consumer search. Candidate-side ambiguity was confirmed by source review, not newly replayed. No candidate implementation, full pytest replay, exact-current-main execution, before/after parity, optimized performance, global consumer closure or measured human comprehension has been established. Static SCC derivation is not canonical runtime resolution. Current main compare has been refreshed: no changed path in either survey source root since the pinned evidence. Reconfirm exact main and impact before starting P1; reproduce baseline counterexamples and existing tests before edits. No implementation, test deletion, workflow/CI policy change, physics changes, merge or architecture acceptance authorized by this document.

**Next gate:** approve only the bounded P1 implementation/validation contract after exact-main baseline and impact refresh. Then reproduce baseline, perform the limited correction, verify public Boundary/Candidate/Behavior/Blind/Gate negative and normal controls, run exact-head CI and separately review. P2–P6 are not completion prerequisites. Keep PR documentation-only and draft pending review.
