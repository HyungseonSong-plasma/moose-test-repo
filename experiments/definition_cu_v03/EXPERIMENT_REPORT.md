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
