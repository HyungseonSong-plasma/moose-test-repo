# P3-X partial integration handoff (source-only) — 2026-11-17

**Final current verdict:** `PASS_PRODUCTION_NEWONLY_STAGE_AND_P3X_SHADOW_10OWNERS / HOLD_NATIVE_RUNTIME_AND_FULL_P3_X`.

- Source PR #665 exact HEAD: `9c15a4f0e2cf8042cb0d4b2f18af31511021d168` (unchanged).
- #668 stage: [Draft PR #674](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/674), stacked at head `4185d04ccded7fe1f6b6da8a5ecc2d0cdf339d75`, **not merged**.
- #668 source-only Production CI: [Run #44199587771](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44199587771), artifact `14380831538`, independently verified ZIP SHA256 `3e6468c6fa96c41387415d88b9f9b7b2d16bdc622ea469e1bb88840132f33683`.

## What passed

1. Production runner now stages both **actual 11-layer New-only** inputs, both corresponding New-only JSON files and the **historical prepared 42-row** electron-moments table (SHA256 `35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b`) in the right physical location. S6-417/941 each old ion FV 26→0 source-only, no Native execution.
2. Independently downloaded the complete #674 CI artifact and checked ZIP, both 11/11 file SHA, each New-only JSON, overlay, 42-row table, Maxwell child/includes/mesh evidence. New-only electron transport is typed `lookup/reduced/clamp`.
3. Located and exact-HEAD checked **19/30** distinct P3 worker receipts. Superseded G1 preflight branch is not double-counted. **Missing 11:** `T5`, `G2`, `G6`, `F8`, `N3`, `N5`, `N6`, `V1–V4`.
4. Found **10 collision candidates per case in PR674 physical stage**: 8 retained explicit electron FEM BCs (`log_e` particle 4; `log_e_energy` energy 4) plus `FunctorMaterials/electron_physical_density` (publishes `n_e_physical`) and `FunctorMaterials/electron_wall_flux` (publishes `e_wall_number_flux`). The New-only `PlasmasAction::act(add_bc)` emits all 8 e BCs from JSON, and `DDEnergyEq::addFunctorMaterials` emits the two same canonical Functors. This is a real *source-level ownership collision*, **not** a completed Native diagnostic.
5. Executed an **independent disposable-copy only** shadow reduction: remove those exact 10 owner blocks with pinned original block SHA, in each case. C0 file SHA `39826e1e95372d226cca4036b520a7f13dfd79c8b6ef0ca2d7c0ca49f904e17e` → `d78a084434eca25b9ece07138c49bf93800845f5947f5ec327bfc81334daa17a`; 10 other .i layers, New-only JSON and 42-row table remain byte-identical. Negative controls **8/8 rejected**. Local shadow ZIP SHA256 `86867d92a1260d4c13fecf10612c39169f2ebf970a1effb60d56d9433ddb5eb3`. This is **not** applied to PR674, production Runner, or Native warehouse.

## Remaining hard gates — in required order

1. Ensure the stacked PR674 integration source and exact HEAD policy are reconciled with PR665; do not accidentally test the old PR665-only pipeline.
2. Finish 11 missing worker receipts; check all signed input/owner/pressure/neutral/RF lineage against the same exact stage.
3. P3-X production implementation: perform fail-closed **10 exact block** electron owner retirement in actual New-only disposable Scratch, with 11-file before/after SHA, unchanged non-target bytes and 8 FEM BC boundary partition. Preserve unrelated `electron_molar_density`, `electron_molar_energy_density`, 7 Maxwell Transfers, PID, Poisson/neutral/Lower-D and original aliases until verified.
4. Prove in **actual Native C++ Warehouse** all 8 electron FEM BCs are singletons and both canonical Functors `n_e_physical` and `e_wall_number_flux` have exactly one live producer. Check electron IC / Energy time, drift, Joule, pressure/neutral, diagnostics and dynamic Maxwell late binding.
5. #671 P5 performs exact binary-HEAD `physics-opt --check-input` separately for both cases. Current Native P2/P3/P4 all **NOT_RUN**, Physics 24 owner runtime **NOT_RUN**, science **SCIENCE_HOLD**.

## Immutable evidence in this branch

- [Worker receipt index](worker_receipt_index.json)
- [Inventory](inventory.json)
- [Producer/consumer edges](source_consumer_edges.json)
- [Bounded verification receipt](verification_receipt.json)
- [10-owner shadow proof](shadow_cutover_10owners.json)

Safety: no private EI raw table bytes, no main/PR665/PR674 modification, no Native solve, no P05 relaxation or workflow skips.
