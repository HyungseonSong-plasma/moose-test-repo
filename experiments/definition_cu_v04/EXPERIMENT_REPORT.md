# Definition CU v0.4 — source scope and name-context falsification

**Scope:** Pilot, not a CU quality verdict or an automatic refactor gate.

## Receipt

- Exact immutable Git source: `moose-test-repo@3e5486ae257cda0aa36065c692d8f32f68e319d9`.
- Verified via [Harness Code CI #45064377034](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45064377034): **296 passed**.
- All **37** tracked production Python `.py` files in `physics_harness/code/{graph,diagnostics,analysis,refactor,verification,delete}`: 8, 12, 10, 3, 3, 1.
- Original bytes come from the existing `GitSourceProvider` Git-tree/Blob store. No worktree or README fallback. A per-source AST witness preserves exact `path:line@blob_sha`.
- Source imports are categorized as **WITHIN_OWNER_CANDIDATE**, **CROSS_OWNER_CANDIDATE**, or external/unresolved; use is not promoted to ownership.
- Python-only inventory is complete within the tracked selected production source set, **not** all languages, generated sources, dynamic imports, runtime behavior or external consumers.

## Measured summary

| Folder | Files | Name-blind role candidate | DEB | MRC (additional cues) | Name vs sibling negative controls |
| --- | ---: | --- | ---: | ---: | --- |
| graph | 8 | GRAPH_MODEL | 3/3 | unresolved | indistinguishable |
| diagnostics | 12 | SOURCE_FACT_COLLECTION | 3/3 | unresolved | indistinguishable |
| analysis | 10 | GRAPH_ANALYSIS | 2/3 | 2 | indistinguishable |
| refactor | 3 | CHANGE_PLANNING | 3/3 | unresolved | indistinguishable |
| verification | 3 | SOURCE_VERIFICATION | 2/3 | unresolved | lexically distinct |
| delete | 1 | unresolved | n/a | n/a | n/a |

Full compact machine-readable result: `measurements.json`. Re-run the uncached source analysis from a full checkout using:

```bash
python -m experiments.definition_cu_v04.measure --root . --expected-revision <40-hex-head> --output /tmp/definition-cu.json
```

## Falsification result

The current lexical entailment protocol recovers few of the behavior-derived clauses through the allowed names and visible context. It distinguishes `verification` from its siblings but **not** `graph`, `diagnostics`, `analysis`, or `refactor`. Thus **high DEB/null MRC must not be interpreted as a bad directory name, poor structure, or low CU**; the cue lexicon itself lacks semantic coverage. No human comprehension tasks or calibrated ground truth were collected.

Definition roles remain *predefined static behavior signatures* and are not a universal semantic inference engine. Unexpected dynamic calls and mixed roles must stay unresolved or qualified. Generalization to code snippets, C++/MOOSE, resolved call targets, IO effects, and multi-facet ownership are separate follow-on work.

The pilot changed no code directory names, READMEs, or code lifecycle. Generic operations `COMPRESS` and `REMOVE` remain planning alternatives requiring independent verification.
