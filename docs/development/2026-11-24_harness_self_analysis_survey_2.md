# 조사#2 — Harness Code / Libs: evidence refinement and solution lucidity

**Status:** RESEARCH; follow-up to [Survey #1 / PR #853](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/853). Not an architecture authority, implementation approval or deletion permission.  
**Pinned source:** [2bf977e17fa2e4eb84b24bce51a717bc76be60f7](https://github.com/HyungseonSong-plasma/moose-test-repo/commit/2bf977e17fa2e4eb84b24bce51a717bc76be60f7). Main remained unchanged during the investigation.  
**Scope:** physics_harness/code and libs. Existing Graph, Diagnostics, Analysis, Code Lucidity and Refactor Planning APIs; no new production engine.

## 1. Correct the gaps in Survey #1

Survey #1 identified candidates but did not establish that commonization improves clarity, that dependency cycles represent defective responsibility allocation, or that high branch counts prove excessive responsibility. It did not directly execute Lucidity/Planning, measure actual Usage Matrix cost, replay the declaration ambiguity, or conduct a repository-wide compatibility search. This survey fills those gaps with bounded evidence, retaining what cannot be proven.

### Evidence ledger

- [Original broad scan #45411795969](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45411795969), artifact 14928832103, SHA-256 f91cf4bd3a761b13dfc76a8816595ee323fdc0d08f3f506ebccd5e4dced01bc7, independently rechecked locally. Full Graph 103,855 nodes / 316,742 edges / 317,941 evidence.
- [Isolated run #45417660394](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45417660394), first measurement and counterexample; execution SUCCESS. Two target selectors inadvertently selected call-site nodes instead of declarations (R04/R06); their metrics are superseded, not used as declaration evidence.
- [Corrected run #45417861526](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45417861526), job 138528913826, exact original source checkout asserted; all steps SUCCESS. [Artifact 14931164970](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45417861526/artifacts/14931164970), downloaded ZIP SHA-256 9d259ca5b4f8c1342a1357f00a5ba1b72fe2e4579430ab85dd4241be99ebf932 independently matched. [Executed reproducibility script in temporary workflow](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/6b1f53e0dff88d9d80367f664d83746050dc7937/.github/workflows/harness-survey-02-once.yml). Temporary workflow removed after capture (097e7ab9682c47eac91b6fb26733d8cca4ad38d8); no active Workflow diff in this PR.
- Durable structured observations: [survey_2_evidence.json](2026-11-24_harness_self_analysis_survey_2_evidence.json), parsed from exact job logs. This is not a byte-for-byte copy of the artifact JSON; artifact has separate verified hash.

Corrected run used Python 3.11.18, GitSourceProvider, run_scan with python_ast, includes physics_harness/code/*.py and libs/*.py. 110 files, SCANNED 91 / UNRESOLVED 19, nodes 11,847 / edges 34,208 / evidence 34,318; PARTIAL/UNVERIFIED, unresolved 94, verification failures 0. Scope ID scope:32f77b3d23dbea3882fe19257c3328103deba8f75b787d14d26ff2fc5ee38414. Scan 2.305 s on this runner. Source scope is narrower than the original broad artifact; counts cannot be directly interpreted as changes to the source.

## 2. Structural analysis — separate observation from interpretation

Rechecked prior import rows against original broad artifact derived data: 721 internal import-specifier candidates, 278 unique non-self file pairs, 168 non-test file pairs. Nine candidates enter scope from two repository files: ci/guards/verify_harness_dependencies.py (5) and ci/guards/tests/test_dependency_contract.py (4). Do not infer global consumer closure.

Reproduction method: read Graph nodes, IMPORTS_CANDIDATE edges and receipt file paths; map tracked .py paths to dotted names, collapse __init__ to package; resolve relative module specifiers from source package, prefer a tracked submodule for from-import if present, otherwise map to package/module file. Retain evidence IDs and discriminator (line:column:alias index). Deduplicate non-self (source,target) pairs; exclude tests for SCC; calculate SCC with all edges, then remove edges incident to __init__.py, then separately retain only column-zero import candidates. This is a syntactic path resolution, not Python import execution; column-zero is only a proxy for module-level imports.

| Filter | Nontrivial SCCs |
|---|---|
| All non-test candidate pairs | One, 22 files |
| No __init__ endpoints | Two, 7 and 2 files |
| Column zero only | None |

The 7-module group is collector.py, assemble.py, receipt.py and providers cpp, moose_input, python_ast, workflow. Witness: collector.py:157-166 loads assembler/receipt/providers inside run_scan; assemble.py:8 and receipt.py:9 depend on collector contracts; providers import FactBatch, SourceInput and ID helpers from collector. This is a composition/contract coupling, not proof of a runtime import failure. Avoid extracting a generic framework just to make the SCC number zero. A possible minimal seam is separating the stable source/collector contracts from scan orchestration *only if* import fan-out or change isolation is materially improved.

The 2-module group is refactor/naming.py:462 -> verification/naming_provenance.py, which imports NamingCase at line 13. Separate ownership of naming decision and evidence authenticity is meaningful. A type-only annotation change is insufficient if isinstance validation is needed.

S01/R12: ci/contracts/harness_dependencies.json defines eight outer physics_harness packages; code subpackages are not members. verification/dependencies.py:_package resolves the outer package, and verify_dependencies intentionally does not prove relative/dynamic imports. Repository CI PASS cannot establish absence of Code-internal cycles. Do not expand CI in research; investigate scope-specific dependency contract first.

## 3. R04 — confirmed declaration identity defect, priority correctness

Source: naming_boundary.py:95-125 builds duplicate keys, then :225 indexes by key (last wins); naming_behavior.py:53-66 overwrites same key; naming_semantic_review.py:100-142 uses first matching declaration. python_ast assigns occurrence-qualified identities instead.

Actual original APIs executed against isolated temporary Git fixtures with immutable blob references:

```python
def transform(x):
    return x + 1

def transform(x):
    return x - 1
```

| Observation | Unique control | Duplicate case |
|---|---|---|
| Boundary result | STRUCTURE_WITNESSED | STRUCTURE_WITNESSED |
| Behavior selector line | 1 | 4 |
| Blinded excerpt anchored at line 4 | n/a | incorrectly returns line 1 body (x + 1) |
| Boundary / packet unresolved | [] / [] | [] / [] |

Duplicate blob b4298735b38d0b804cbbc5cd2d2edc19f6a54347; source_ref sample.py:4@that blob contains the second function, but its packet code equals the first. Control blob 73bca47390c4e0c82369c06ecaad4ae2dc427a4f. Both runs reproduce the defect. This proves an evidence-binding defect, not semantic incompatibility of the current production Harness or a successful edit.

Compare alternatives: KEEP (known defect persists); broad AST unification (too large); minimal fail-closed on ambiguous declaration identity plus exact anchor-to-excerpt validation (preferred first candidate). Reuse current occurrence identity if practical, rather than inventing global symbol keys. Preserve unique control, duplicate function/class/method cases, overloads, property accessors, nested declarations, async/signature/encoding distinctions; verify all source refs and excerpts. Do not silently pick first or last; retain HOLD for unsupported identity. No implementation yet.

## 4. Functional and lucidity evidence — actual API results

Corrected run executed assess_code_understandability, summarize_understandability, interpret_understandability_indicators, build_planning_context and review_alternatives at exact source. Declaration kind explicitly selected (not call-site name). For each target compare KEEP and bounded CHANGE with source evidence, stated benefit/risk, no self-attested PASS. No universal score.

| Candidate / function | LOC | Branches | Nesting | Branch density | Candidate-call density |
|---|---:|---:|---:|---:|---:|
| R01 GitSourceProvider.inventory | 27 | 8 | 3 | .2963 | .8148 |
| R02 evaluate_naming_safety_gates | 60 | 5 | 2 | .0833 | .5667 |
| R03 build_usage_matrix | 144 | 27 | 5 | .1875 | .4792 |
| R04 _symbol_inventory | 31 | 6 | 6 | .1935 | .3548 |
| R05 GraphAssembler.assemble | 128 | 26 | 4 | .2031 | .5078 |
| R06 _scan_revision | 67 | 22 | 9 | .3284 | .6716 |
| Control run_scan | 197 | 36 | 4 | .1827 | unavailable |
| R11 derive_indicators | 38 | 4 | 2 | .1053 | .4474 |

Full 110-file scope: all 8 KEEP/CHANGE pairs HOLD, recommended_id null. Narrow exact-file scope: R01-R06 and R11 COMPLETE/VERIFIED, both options ADMISSIBLE, recommended_id null (four unknowns each). run_scan remains PARTIAL/UNVERIFIED and HOLD/HOLD even in narrow scope (15 unknowns). Narrowing makes source-local evidence admissible; does not remove external/semantic/behavior obligations. Keep as a negative control rather than interpret length as proof that run_scan should be split. CHANGE checks include exact before/after receipt parity, impacted tests at after HEAD, behavioral compatibility and graph diff. API assessments are not measured human comprehension or proof of benefit.

## 5. R03 — real timing, corrected priority

Existing build_usage_matrix executed three times per target count on same 34,208-edge scoped Graph, selected first distinct non-test function declarations in deterministic Graph order; CALLS_CANDIDATE FORWARD, DEFINES ignored, required path and external/runtime uncertainty declared. Both runs used same workload, not an optimized implementation.

| Targets | First run median ms | Corrected run median ms | Corrected samples ms | Full edge passes item count |
|---:|---:|---:|---|---:|
| 1 | 19.4 | 22.7 | 34.25, 22.71, 20.95 | 68,416 |
| 10 | 71.6 | 77.4 | 75.56, 77.44, 78.30 | 376,288 |
| 50 | 310.1 | 326.7 | 323.59, 399.84, 326.66 | 1,744,608 |

Repeat work is real and scaling is visible; absolute cost is modest here. No full-repository timing or optimized speedup measured. Prefer existing adjacency reuse inside Usage Matrix before introducing a generic cache or changing Graph. Lucidity adapter and planning context also traverse graph per target; only extend when actual workload demands it. Compare KEEP; require identical rows, evidence, unresolved, direction/filter and cross-HEAD treatment, plus measured time and memory.

## 6. R09 — compatibility consumers (bounded)

Exact-commit git grep across tracked repository and owner-scoped GitHub code search (top 50 per query, indexed default branches). Graph imports were cross-checked; literal search also captures dynamic-import test strings and documentation. Counts are matching lines, overlapping token prefixes, not unique consumers.

| Search token | Tracked matching lines |
|---|---:|
| libs.code_understandability | 6 |
| analysis.understandability_adapter | 2 |
| analysis.understandability_interpretation | 1 |
| analysis.lucidity_adapter | 9 |
| analysis.lucidity_interpretation | 5 |
| verification.naming_replay | 3 |
| verification.naming_replay_execution | 1 |

Owner-wide indexed search returned hits only in moose-test-repo for these names. Legacy understandability/naming replay references are predominantly explicit compatibility tests/README; stable lucidity_adapter/interpretation paths are used by integration tests, layout tests, shims and documented API. Treat 8 legacy paths separately from 2 stable API paths. Stable APIs KEEP; legacy HOLD pending explicit retirement policy and external/dynamic/serialized consumer verification. Unindexed private repos, installations, generated paths, alias-built dynamic references and external consumers remain unknown; no deletion.

## 7. Candidate decisions — minimum intuitive solution, not an implementation plan

| ID | Revised priority / status | Minimal direction and counterargument |
|---|---|---|
| R04 | First: reproduced correctness defect | Ambiguity fail-closed and exact declaration/excerpt consistency; not a broad AST engine |
| R01 | High: ownership | Extend existing provider for immutable inventory/commit/ancestry as needed, preserve HEAD contract and filters; no separate Git library, do not expose raw _git |
| R02 | High investigation / no speedup claim | Reuse verified source bytes and AST within same trusted execution; candidate-specific judgments and blind review remain independent; not arbitrary receipt reuse or persistent cache |
| R03 | Medium: measured scaling, small local latency | Use existing adjacency/index inside batch; do not modify Graph model; compare before/after time/memory if approved |
| R05 | Medium: ownership/coupling | Source consistency is diagnostic output verification; consider narrow API/ownership seam vs KEEP, maintain independence. Python submodule imports still execute package __init__; no blanket lazy import |
| R06 | Selective | _scan_revision depth 9, _symbol_inventory depth 6: investigate guard clauses/linear flow; preserve behavior/error order. No generic function splitting |
| R07 | Medium/low | Reuse existing git_factory and common witness setup if it preserves independent controls; no new fixture framework or test removal |
| R08 | Low | Share transport only if exact security behavior and need demonstrated; signed archive redirect vs review no-redirect; leave separate otherwise |
| R09 | HOLD / stable API KEEP | External closure unproven; compatibility retirement separately approved |
| R10 | KEEP | Graph model redesign not justified by client-side repeated traversals |
| R11 | KEEP | Numerical metric ownership correct; indicators do not measure semantic cohesion or comprehension |
| R12 | Investigation | Code-level dependency coverage contract gap; no CI policy change |

S02/R04 is the principal finding. Reduce observable ambiguity before reducing file count. A common abstraction is justified only by shared semantics and fewer concepts/call paths for the consumer; stable IDs, independent judgments and evidence authenticity cannot be traded for smaller code.

## 8. Status and remaining boundaries

Investigation supplements completed: exact-source API run and corrected target selection; actual duplicate-declaration reproduction and control; actual baseline performance measurement; bounded tracked and owner-indexed consumer search; reproduced static dependency grouping; explicit KEEP/CHANGE alternatives and uncertainty. No candidate implementation, before/after parity or full pytest replay was performed; no full external consumer closure, runtime semantics, complete coverage or empirical human comprehension claim. R01/R02/R05 remain hypotheses for design comparison, not proven defects/speedups. Structural resolution is a static supplementary analysis; not canonical runtime resolution. Direct local clone still failed DNS; actual source was checked out on GitHub Actions. Temporary branch-only execution workflow removed; final PR diff contains research documents only, no production code, API, tests, CI or Workflow changes. Survey #1 remains separate draft; no merge or implementation approval.

**Result:** RESEARCH / Survey #2 evidence captured / R04 first candidate for subsequent design review / all edits HOLD pending approval.
