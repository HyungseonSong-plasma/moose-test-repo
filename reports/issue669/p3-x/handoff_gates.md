# Issue #669 P3-X — production source-only cutover handoff

**Scope:** S6 recovery-package P3-X, not Native/Science P3. Exact PR #665 source base `b5c1de717bd944bfa11685e826a922fbb6ae483a`, original P1-0 staged inputs pin `9c15a4f0e2cf8042cb0d4b2f18af31511021d168`.

## Source-bound PASS — actual Production Runner

- The existing `prepare_s6_run_input.py --newonly` now invokes `prepare_s6_newonly.py` plus `retire_s6_electron_newonly_owners.py`; **P3-X electron preflight occurs before P2 writes**, after 11 exact P1 source SHA and immutable JSON/Maxwell/electron transport validation.
- S6-417 and S6-941 each physically stage 11 .i layers, 8-reaction JSON, original 42-row prepared electron lookup table, Maxwell child/includes/mesh. Each first retires **26 Native ion FV owners** and then **8 electron FEM BC + 2 electron FunctorMaterial** exact-byte owners in disposable Scratch, using section/name/type/variable/boundary/old-block SHA pins; no unrelated input or source files changed.
- **CI #44256823392 SUCCESS** at P3-X implementation HEAD `556f104d62cce635dcf7b59bf6966400b0b1fa18`. [Artifact #14405784430](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44256823392/artifacts/14405784430) ZIP SHA-256 `9e6e8a646e3c3706e56b681c2a272081fbb55aaf74c4914f52c9db37507d0de6`. Independent post-download readback rehashed **22/22** actual input files and reconstructed **72/72** deleted old block byte hashes. Exactly five layers remain byte-identical to original P1 source per case, only the four ion overlays + C0 with ion/electron removals + 11th Physics overlay changed.
- Old `electron_physical_density` and `electron_wall_flux` producers that would collide with generated `n_e_physical` and `e_wall_number_flux` are absent from the actual stage. The three non-target electron derived materials `electron_molar_density`, `electron_molar_energy_density`, `electron_physical_energy_density`, the solved `pressure` and `neutral_outlet_p`, plus RF energy `rf_heating_t6` are retained exactly.
- The CI rejects **28/28 direct P3-X owner/JSON/pressure mutation tests** before any write, in addition to **8/8 P2 full-CLI fail-closed cases**. A previous successful source stage Artifact #14405638218 shares **178/179 byte-identical files** with the final run; only aggregate negative-test receipt expanded.
- Task-isolated receipts **30/30**, including newly completed `P3-T5`, `P3-G2`, `P3-G6`, `P3-N3`; the other 26 historical source-bound Git blobs were independently reread. [Worker receipt index](worker_receipt_index.json), [inventory](inventory.json), [producer/consumer graph](source_consumer_edges.json), [integration receipt](verification_receipt.json).

## Explicit HOLD / next gates

1. **P4-X #670:** actual New-only ion Source 5→3 and Poisson/WallFlux/SurfaceCurrent/diagnostics consumer cutover. Preserve all archived source identity and Maxwell/RF pressure semantics.
2. **P5 #671 Native P2:** execute the exact final updated PR #665 HEAD for S6-417 and S6-941 using the same PhysicsApp binary SHA and **real** `physics-opt --check-input`. Independently prove exactly 8 generated electron FEM BC objects, unique `n_e_physical`/`e_wall_number_flux` Functors and generated ion 12 Kernel + 12 BC objects; no old Native duplications, no missing dynamic Warehouse/Functor caller.
3. **D8:** historical active-caller lineage and actual Maxwell child/includes/mesh byte staging are PASS_BOUNDED; **New-only runtime** Warehouse/Functor and child dynamic bindings **HOLD**. Do not substitute historical child tolerance or claim zero active callers.
4. Physics24 runtime NOT_RUN, Native P2/P3/P4 NOT_RUN, SCIENCE_HOLD. No long-running solve, no private EI rate raw bytes, no bypass of P05 duplicate checks or `dont_create_kernels`, no main merge.

**Result:** `P3_X_SOURCE_ONLY_CUTOVER=PASS / P3_X_NATIVE_ACCEPTANCE=HOLD`. Evidence and code are in a dedicated integration branch until separately merged into Draft PR #665.
