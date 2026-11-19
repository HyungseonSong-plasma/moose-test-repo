# FDEG Structural Evidence v0.2 — Consumer binding and identity contract

**Owner:** Issue #691 / Draft PR #692. **Scope:** P0 static structure only; never caller-zero or retirement authorization.

## Change from v0.1

v0.2 retains the v0.1 scanner's original relationship kinds and `from`, `to`, `relation`, `strength`, `detail`, `evidence` fields, with these additive and identity-bound changes:

- Report `schema: "fdeg.structural.v0.2"`, deterministic `graph_id` (SHA-256 of canonical entire report excluding `graph_id`).
- Every `edges[]` record has a content-addressed `edge_id`; it hashes source/destination, relation/strength/detail, path/line/blob/excerpt.
- Input type instances become explicit `instance:...` nodes, linked by `file -> DECLARES_INSTANCE -> instance -> INPUT_INSTANTIATES -> class`.
- `instances[]` contains `instance_id`, `input_path`, `block_path`, `factory_type`, `type_line`, `structural_edge_id`, `bindings[]` (declared names/raw values/line) and source blob identity.
- Exact `repository_head` and each source `blob_sha` remain mandatory to join externally proven Functional claims.

No capability is inferred from class name, lexical mentions or an input type declaration. `bindings` are **raw, declared .i values**, not effective MOOSE defaults, resolved Functors, runtime arguments or physics variables. `!include` is a static relation, not evaluated input expansion. Repeated/overridden/generated inputs and dynamic values must be interpreted by downstream Coverage, not silently resolved here.

## Stable single-target command

```bash
python3 ci/guards/fdeg_structural.py \
  --target PhysicsFVElectronReactionSource \
  --expected-head "$(git rev-parse HEAD)" \
  --output /tmp/fdeg-structural.json
python3 -m unittest discover -s tests -p test_fdeg_structural.py -v
```

## Join contract

Functional consumes exact `schema`, `target`, `repository_head`, `graph_id` and `edge_id`. All identity claims are checked. A stale/reordered-but-changed/forged graph, unresolved consumer, unknown runtime binding, or missing evidence **cannot** yield `SAFE_TO_DELETE`. Functional must not silently reclassify `MENTIONS_SYMBOL`, `DECLARED_INPUT_ONLY`, or `LEXICAL_FLOW_CANDIDATE` as a native runtime observation.

Graph IDs are content-addressed, not persistent across changes to input, paths, worktree, or source SHA. The previous v0.1 JSON is not accepted by Functional v0.1 as an equivalent report: regenerate v0.2 from the same exact source HEAD.

## Validation

P0 checks cover deterministic graph/edge ID generation, input parameter bindings, type aliases, indirect workflow and included .i paths, Action syntax, dynamic/unresolved paths, malformed sources, SHA mismatch and binding mutation. Native P1/P2/P3, external callers and physical significance are not established by this scanner.
