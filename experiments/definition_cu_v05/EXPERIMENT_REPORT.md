# Definition CU v0.5 — contrastive naming discriminability

**Status:** experimental discriminator implemented; **human CU and naming-alignment decision: HOLD**.

## Intent

Replace v0.4's word-overlap-only naming verdict with an independently supplied
**source-definition signature** and a competitive name→definition identification
protocol. A short contextual name is allowed; the evaluation must identify
*which* definition the name/context suggests, not penalize length.

## Methods and source separation

1. The unchanged v0.4 Python-AST evidence extractor infers roles from exact
   `GitSourceProvider` Git-tree/blob source **without target folder names or README**.
2. Only behavior witness kinds required by the inferred role are mapped to
   explicit meaning facets, preserving `path:line@blob_sha`. No string similarity
   to the role ID is considered by the discriminator.
3. A *separate, versioned and manually authored* English concept lexicon maps
   the name/parent/direct-module/public-API disclosure cues to candidate facets.
4. Five observed role candidates compete with five **synthetic hard negatives**:
   relation interpretation, source parsing, change execution, relation
   serialization and provenance logging. They are NOT real repository entities.
5. Progressive disclosure tiers: name (0), parent (1), direct public module (2),
   package `__all__` public API (3). Unique top match is `DISTINCT`; tied top
   matches are `AMBIGUOUS`; zero overlap `ABSTAIN`; a unique wrong choice `WRONG`.
6. The finite-cue DP finds the best-case *minimum optional cues* to select the
   source reference. This does **not** guarantee that disclosing every later cue
   leaves the choice correct. `stable_correct_tier` explicitly checks that.
7. Report blank-name and sibling-swapped-name counterfactuals, with identical
   source signature and all other context fixed. No quality or mutation
   determination is made.

## Frozen, source-anchored comparative pilot

Frozen role witness lines and API names were read at
`moose-test-repo@40d5af8819c1b27fd5b5903ec07910669a37748a`; references are
bound to actual Git blobs. **`frozen_reference_cues.json` is a curated receipt of
selected existing observations and public names, not a new full-source scan.**
The live `measure.py` independently performs the full v0.4 Git-source scan on
its current HEAD and will be exercised by Harness Code CI.

5 source-derived role references + 5 synthetic hard negatives:

| Folder | T0: name only | T3: all visible context | Stable correct tier | Best-case extra cues |
| --- | --- | --- | ---: | ---: |
| `graph/` | AMBIGUOUS | DISTINCT | 2 | 1 |
| `diagnostics/` | ABSTAIN | AMBIGUOUS | — | 1 |
| `analysis/` | AMBIGUOUS | AMBIGUOUS | — | 1 |
| `refactor/` | WRONG (execution decoy) | DISTINCT | 3 | 1 |
| `verification/` | AMBIGUOUS | DISTINCT | 3 | 1 |
| `delete/` | no source-supported definition | unresolved | — | N/A |

- **Name-only source-reference proxy accuracy:** 0/5 (0%).
- **Full-context source-reference proxy accuracy:** 3/5 (60%).
- **Blanked name with identical full context:** 3/5 (60%).
- **One sibling-name substitution per case with identical context:** 3/5 (60%).
- **Measured incremental advantage of original names over both controls: 0/5.**
- `analysis/` is correctly distinguished at tier 2 but returns to ambiguity at
  tier 3: more API words can *reduce* discriminability under this model.
- `diagnostics/` can be identified via a selectively chosen cue, yet the
  *entire* public API context makes the full-set classification ambiguous.

This is an important **negative result**: the current model has partial
behavior→concept→name identification performance, but does **not** demonstrate
that existing folder names aid understanding beyond their visible APIs. The
name-aware model does not yet justify any rename, document compaction or removal.

### Not measured / limitations

- **DDA is a source-reference identification proxy**, not independent human
  ground truth. Source signatures and the lexicon were manually specified in
  this repository context; full generalization is unknown.
- The per-tier `surrogate_gain_bits = log2(N / top_tie_count)` assumes a *uniform
  model-only shortlist*. It is **not empirical Context Information Gain** or
  a calibrated probability. Incorrect unique selections can have high proxy
  information gain; never optimize this scalar alone.
- Candidate-set composition matters. An identically meaningful decoy makes
  even an ideal matcher abstain. The controls are not a random sample.
- No out-of-repository holdout, independent human judge, latency/navigation
  observation, C++/MOOSE runtime semantics, or external-consumer closure.
- Full-source coverage remains **tracked Python only** within the previously
  selected Code folders; it is not all code or all user-facing context.
- The ontology does not reason over compositional relationships or provenance
  ownership of individual public API cues. The v0.5 negative observations
  indicate these as candidates for a separate falsifiable improvement.

## Execution

From an exact Git checkout with the existing Harness dependencies:

```bash
python -m experiments.definition_cu_v05.measure --root . --expected-revision "$(git rev-parse HEAD)" --output /tmp/definition_cu_v05.json
python -m experiments.definition_cu_v05.replay_frozen > /tmp/definition_cu_v05_frozen.json
python -m pytest -q physics_harness/code/tests
```

All commands are read-only with respect to the repository (the explicit output
path is outside the checkout). The solver is not executed; no files are renamed,
compressed, removed, or auto-modified.

## Acceptance boundary — human-evaluation workstream stopped (2026-11-23)

By decision for Issue #767, **independently adjudicated reference answers** and
**actual blinded human evaluation** are stopped and are **not required** to
accept this bounded read-only Definition CU experiment. Do not schedule new
human trials or hold the pull request solely for human calibration.

Evaluate the implemented scope on source-bound evidence alone:
- exact Git revision and blob provenance, name/README exclusion from source
  definition inference, and input/scope fail-closed behavior;
- reproducible original frozen-source pilot and explicit 5-role plus
  5 synthetic-negative contrast (the synthetic controls are not people);
- deterministic P0, rename/blank/sibling-name counterfactuals, stable-context
  discrimination and abstention/ambiguity handling;
- clean relevant exact-HEAD CI and ordinary source/code review.

**Interpretation boundary:** DEB/MRC, discriminability and CIG/DDA proxy
quantities are **not human-validated CU or universal quality scores**.
A 0/5 original-name advantage is a negative result under the versioned
lexicon/pilot only, not evidence that naming is defective. Unknown external,
dynamic, non-Python and semantic-consumer scope stays explicitly unknown.
No automatic rename, COMPRESS, REMOVE, production code changes or CI blocking
based on these exploratory proxy scores is authorized.

The previously implemented optional blinded-response audit and its five
synthetic tests have been withdrawn from the PR because that workstream
is stopped. Its historic commit remains in the PR Git history but it is
not part of the proposed integrated source tree.
