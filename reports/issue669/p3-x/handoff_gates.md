# P3-X source-only integration handoff — exact HEAD

**Verdict:** `SOURCE_ONLY_PREINTEGRATION_PASS / FULL_P3_X_HOLD`.

Immutable integration HEAD: `9c15a4f0e2cf8042cb0d4b2f18af31511021d168` (PR #665).

This dedicated branch is evidence-only; it does not implement the protected production cutover.

## Completed within existing gates

- Independently rehashed P1-0 final Hybrid 11 inputs for each case against source artifact #14372315897 and #668 11-input post-retirement case artifacts #14379920938.
- S6-417 and S6-941: Native ion owners 14 FV Kernel + 12 FV BC removed to zero, with 5 changed / 6 unchanged files. Reconstructed all 26 exact removed blocks from actual P1 bytes; **all non-target bytes preserved**.
- Verified 8 *non-ion* electron FEM BC owners in each case remain byte-identical through #668 Scratch ion retirement. Particle and energy boundary families each cover 6 sidesets exactly once in existing Hybrid.
- Verified fixed source contracts: two typed New-only electron transport records are `{type: lookup, unit: reduced, bounds_policy: clamp}`. Correct historical 400W prepared table is **42 rows, SHA-256 `35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b`**, **not** the tracked default 100-row SHA `994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387`.
- Rejected 8/8 local source-only mutation controls; read and indexed 19 distinct task receipts at source HEAD, plus one superseded G1 preflight receipt. **11 worker receipts missing**.

## Exact remaining worker IDs

`P3-T5`, `P3-G2`, `P3-G6`, `P3-F8`, `P3-N3`, `P3-N5`, `P3-N6`, `P3-V1`, `P3-V2`, `P3-V3`, `P3-V4`.

## Blocking sequence — do not bypass

1. **#668 P2:** Connect actual production runner to exact-pinned `retire_in_disposable_scratch`, stage both `unified_s6_{417,941}_newonly.json` and exact New-only eleventh continuity/energy overlays in each disposable Scratch. Preserve 26 old-owner zero check, original identities, Maxwell child/includes/mesh, and pressure/RF/neutral consumers. Rehash before/after all 11 staged inputs **and JSON** in **each** case.
2. Stage the **actual historical 42-row `electron_moments.txt`** in each output runtime location. Check runtime relative path resolution and byte SHA; fail closed if the tracked 100-row file was used or path breaks.
3. **P3-X cutover:** Before enabling JSON electron-wall BC generation, retire or otherwise prove no simultaneous contributions by existing 8 Hybrid `[BCs]` electron particle/energy owners; record all eight before/after block SHA and exact 6 sidesets in each family. Neither the present Hybrid names nor the New-only JSON e-boundary names imply uniqueness by themselves.
4. Bind `log_e`, `log_e_energy` and their unique JSON/C++ initial owner; validate `[Energy] transport_coefficient=fluid`, FEM potential, mean-energy/material providers. Protect active diagnostics, 7 Maxwell Transfers, PID, pressure-neutral/Rhie-Chow, and Poisson/Lower-D.
5. Complete the 11 missing worker receipts and independently re-run negative tests for missing/duplicate owners, wrong electron table unit/bounds/path, IC, energy, 8 FEM BCs, pressure aliases and unreachable dynamic callers.
6. **#671 P5 only:** Execute exact-HEAD/binary `physics-opt --check-input` and inspect real C++ Warehouse/P05 inventory for both cases. Do not infer Native P2 PASS from this static evidence. Native P3/P4 and science equivalence remain NOT_RUN/HOLD.

## Artifact links

- [Worker receipt index](worker_receipt_index.json)
- [Source-only owner inventory](inventory.json)
- [Producer/consumer graph](source_consumer_edges.json)
- [Integrated verifier receipt](verification_receipt.json)
- [P1-0 CI run](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44180190753)
- [#668 Scratch-stage CI run](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44196762787)

**Safety:** No private EI raw tables, no main/PR #665/source mutation, no Native P2/P3/P4, no `dont_create_kernels` bypass, no science acceptance.
