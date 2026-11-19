# code7 PR-A — exact-HEAD FDEG retirement qualification

**Target:** `PhysicsFVThermalDiffusion` (source and header only).
**Baseline branch point:** `main@6bceb311788f418ea7810e0317b582ae1ef7c9b9`.
**Approval:** planning and P0 evidence generation only; `SAFE_DELETE=HOLD`.
**Issues:** #691 (Structural), #701 (Transition), code7 audit #701 comment 7011981933 and lifecycle gap comment 7012050458.

## Evidence objective

For the exact PR HEAD checked out by Repository CI, emit:

- `structural.json` — FDEG Structural v0.3 (tracked source, declared relations, unresolved scope);
- `functional.json` — Functional v0.2 (source-pinned thermal flux contracts);
- `transition.json` — Transition v0.1 (per-consumer dispositions, protected producers, blocking obligations, DAG);
- `summary.json` — source/header Git blob SHA, graph IDs, consumer-role/disposition counts, unresolved/blocker counts, explicit HOLD verdict.

Collector: `ci/guards/code7_retirement_evidence.py --expected-head "$(git rev-parse HEAD)" --output-dir "$RUNNER_TEMP/code7-fdeg"`.
The collector **rejects a dirty or mismatched tracked checkout**, verifies both graph joins through the original modules, preserves scanner incompleteness as evidence, and fails on fake retirement/caller-zero or runtime approval. Repository CI captures four JSONs in a **14-day** artifact named `code7-fdeg-<run_id>-<attempt>`.

## Source-bound findings, not caller-zero

At `main@55472c4cd9f525552d9327ce459e641194e57173`, manual pinned-GitHub-tree review found **0 direct current Factory names** in 153 tracked `.i` files. Three `QPXFVThermalDiffusion` historical declarations in Issue20 are a **different Factory**. Checked 56 PhysicsApp source implementations, 64 headers and Issue402 S6 scripts with no named current-class consumers outside the target C/H itself. This review does **not** certify generated/untracked/external consumers or Native activation.

Do not remove `NVTransportMaterial`, `D_T_<species>` producers, other Functor owners or Issue20 historical sources. The current policy has no approved functional replacement. `include_thermal_diffusion=false` or `grad(T)=0` in any one case is not global no-use.

## Next gates

1. **G1 readback:** exact PR HEAD, three graph identities, complete JSON artifact, unresolved list and consumer-disposition review. If generator, provider or current runtime remains unknown, record blocker rather than inventing a caller-zero verdict.
2. **G2 dynamic/generated scope:** stage supported New-only 417/941 final inputs at immutable PR HEAD; inspect exact object inventory and declared/actual binding, evaluate external scope in owner-approved boundary. Historical `QPXFVThermalDiffusion` replay is separate.
3. **G3 Harness lifecycle fix:** archive frozen active source and S/F/T receipts, add active-to-retired catalog state with mutation checks before deleting C/H. The current Functional source-anchor and ten-profile CI asserts prevent naive file deletion. Coordinate with code1 PR #706 rather than parallel divergent implementations.
4. **G4 isolated delete candidate:** only after G2/G3 owner gates; remove exact C/H/Factory registration on an isolated branch, preserve `NVTransportMaterial` and independent D_T consumers, P1 clean build + P2 final input check + P0 Repository CI + appropriate Native term parity and rollback. No direct merge.

Graph-only P0 is **not** independent scientific or Coverage acceptance. Retirement remains `HOLD` until the required owners review executed evidence.
