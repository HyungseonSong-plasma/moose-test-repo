# Definition evidence v0.3 — partial static-behavior pilot

## Status

- Baseline: Draft PR #768, initial parent `60028f47ec70a5156d898331eaac0e9184dc5daa`.
- Target: five representative Python files (one per folder), plus the empty `delete/__init__.py` control.
- Method: actual Python AST observations, source-bound `path:line@GitBlob` witnesses, exact checked-out revision, explicitly versioned inference predicates, then original DEB/MRC cue-minimization code.
- Target name and README are never used for role inference. Imported *interface and data type* names can still be signals; the inference is NOT completely name-free or behavioral runtime proof.
- No whole-folder scan or global responsibility closure is claimed. Externally called functions remain syntactic candidates, and possible side effects or dynamic behavior remain open.
- Expected bounded roles: `GRAPH_MODEL`, `SOURCE_FACT_COLLECTION`, `GRAPH_ANALYSIS`, `CHANGE_PLANNING`, `SOURCE_VERIFICATION`; `delete/` stays `UNRESOLVED`.

## Reproduce

```sh
PYTHONPATH=. python experiments/definition_cu_v03/measure.py --root . --output /tmp/definition-cue-v03.json
python -m pytest -q physics_harness/code/tests/test_definition_behavior.py physics_harness/code/tests/test_definition_behavior_repository.py
```

The CLI fails on source/blob identity mismatch; `--expected-revision` can require one exact SHA. The result records actual source witnesses and DEB/MRC values. There is no mutation or CI policy change. `MRC_extra_cues: null` means unrecoverable given the allowed extra cues, **not** zero context.

## Gates

1. P0 mutation controls: incorrect blob, mixed revision, empty/out-of-scope sources, ambiguity, dynamic dispatch and side-effect candidates.
2. Real-repository integration: one representative source file per folder is scanned on the exact checked-out commit and target-role hypotheses are checked against independent expectations.
3. Follow-on: characterize false positives on misleading imported interfaces and broaden coverage/consumer closure independently before CU calibration or `COMPRESS`/`REMOVE` decisions.

No documentation is compressed or deleted, and no human-understandability conclusion is made.

## Exact-baseline cue replay (separate from full-source AST execution)

`measure_frozen_baseline.py` consumes the existing exact-blob v0.2 exported-API
snapshot at `main@4f873e71f8503943c9fce2dd30fcc96c28d6f631` and behavior
role hypotheses supported by specific source lines. It does **not** claim to
have executed v0.3 AST extraction over full source files. Results are in
`frozen_baseline_measurements.json`.

| Directory | Hypothesized behavior role | DEB | MRC extra cues |
|---|---|---:|---:|
| graph | GRAPH_MODEL | 3/3 | null |
| diagnostics | SOURCE_FACT_COLLECTION | 3/3 | null |
| analysis | GRAPH_ANALYSIS | 2/3 | 2 |
| refactor | CHANGE_PLANNING | 3/3 | null |
| verification | SOURCE_VERIFICATION | 2/3 | null |
| delete | unresolved | N/A | N/A |

These numbers reflect the **un-calibrated v0.2 lexical cue protocol** and a
role-specific vocabulary, not a cross-folder ranking of actual CU. In fact,
the many `null` values demonstrate a metric limitation: sufficient context
cannot be assumed absent solely because its semantic meaning does not appear
as an exact lexical entailment. This must be addressed before naming/structure
change recommendations. The v0.3 real-repository test exercises AST evidence
on checked-out source independently from this frozen cue replay.
