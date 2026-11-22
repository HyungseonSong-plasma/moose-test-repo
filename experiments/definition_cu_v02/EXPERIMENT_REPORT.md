# Definition Evidence × Code Understandability — DEB/MRC v0.2

**Source:** `HyungseonSong-plasma/moose-test-repo@4f873e71f8503943c9fce2dd30fcc96c28d6f631`  
**Scope:** 6 immediate subpackages of `physics_harness/code/`  
**Input:** pinned six `__init__.py` blob identities, public exports, direct source module inventory  
**Not input:** README text, descriptions, or target folder basename during *definition inference*.  
**Results are exploratory structural/lexical proxies, not a human CU score.**

## Measurement contract

- **Definition inference** runs conjunctive role rules over tokenized *exported symbols*. Each role yields source-linked core concept clauses. A public export alone does not prove runtime behavior or semantic ownership. With an actual checkout, `extract_public_symbols_from_folder` attempts to resolve exported symbols to local source declarations and marks unresolved reexports.
- **DEB** = number of role-defined semantic concepts that cannot be recovered lexically from the target name and direct parent name. Report `numerator/denominator` as well as count. The lexicon explicitly makes `graph → node, edge` and `verification → verify` entailment hypotheses; it is fixed, versioned, and not fit from evaluated target names.
- **MRC** = smallest *additional number of cues* (visible non-private `.py` module basenames, then exposed public API symbol names) needed to recover all the remaining concepts. A dynamic program finds an exact finite-cue minimum and records selected witnesses and maximum disclosure tier. `None` indicates unrecoverable within the declared cue universe. This is **not** the count of human mental steps or actual reader navigation time.
- For ambiguous or missing definition evidence, do not compute metrics; `UNRESOLVED` is not score zero. `KEEP`, `CHANGE`, `COMPRESS`, `REMOVE` remain **generic non-executing alternatives**, not decisions derived from DEB/MRC.

## Measured output

| Target | Role candidate | DEB | MRC (extra cues) | Minimum disclosure | Selected evidence cues |
|---|---|---:|---:|---|---|
| `graph/` | REPRESENT | **2/4** | **1** | Public API | `ClaimEvidenceRef` |
| `diagnostics/` | COLLECT | **3/3** | **3** | Public API | `CppSourceCollector`, `FactBatch`, `ScanBudget` |
| `analysis/` | ANALYZE | **1/3** | **1** | Nearby module | `impact.py` |
| `refactor/` | PLAN | **3/3** | **2** | Public API | `AlternativeReview`, `PlanValidation` |
| `verification/` | VERIFY | **1/3** | **1** | Nearby module | `dependencies.py` |
| `delete/` | UNRESOLVED | N/A | N/A | — | no exported implementation evidence |

**Interpretation:** `diagnostics` and `refactor` impose more lexical explanation burden under this fixed probe than `analysis` or `verification`. That does **not** establish poorer human comprehension, defective architecture, or a need to rename; a short name can be justified by the full contextual meaning. Because the role predicates use API names, this experiment does not yet establish behavior-derived or ground-truth definition correctness. The parent `code/` remains unresolved because it exposes no independent public API.

## Test and controls

Local command: `PYTHONPATH=. python -m pytest -q physics_harness/code/tests/test_definition_cu.py`

**10/10 PASS**: definition unchanged by target folder renaming, empty/ambiguous evidence stays unscored, contextual name can reduce DEB, exact finite-cue set-cover, incomplete context returns unknown, concept budget guard, ownership provenance vs unresolved reexports, fixed lexicon, and invalid source inputs.

## Limitation / next scientific gates

1. Validate exact source declarations against the local checkout and full git HEAD; frozen manifest has pinned blob SHA but is not a full repository execution trace.
2. Upgrade inference to *behavioral* observed inputs, outputs, effects, entrypoints and local ownership before treating definitions as valid descriptions of functionality. Lexical role inference can be fooled by misleading API names.
3. Validate contextual entailments with independently assessed definition-to-name prediction tasks, and measure actual reader accuracy/time/error. Avoid claiming human CU from these proxy values.
4. Document minimization (COMPRESS/REMOVE) additionally requires unique-contract and external-reference retention checks. No README changed or deleted here.
5. MRC context universe currently contains local source stems and exported API symbols; missing external consumers, runtime observations, tests, or deeper source interfaces can change a result.

## Reproduce

From repository root, after placing these files at their proposed paths:

```sh
python -m pytest -q physics_harness/code/tests/test_definition_cu.py
python experiments/definition_cu_v02/measure.py --output /tmp/definition_cu_results.json
# Optional exact-head repository source validation:
python experiments/definition_cu_v02/measure.py --root .
```

The optional `--root` mode rejects HEAD mismatch with the pinned snapshot and checks exports against the actual source tree. It is not valid against later HEADs without refreshing the snapshot and documenting its provenance.
