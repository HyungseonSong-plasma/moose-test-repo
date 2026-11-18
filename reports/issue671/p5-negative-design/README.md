# Issue #671 — P5 remaining Native negative tests: N1, N3, N4, N7

> **DESIGN_ONLY / NATIVE_NOT_RUN / SCIENCE_HOLD.** This is an independent task plan, not a P05 PASS. The machine-readable exact-target matrix is `negative_case_matrix.json`. Neither `main` nor Draft PR #665 nor the shared #671 issue body is changed by this worker.

## Source and scope pin

- At design time Draft PR [#665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) HEAD = `65794d5f33449499349b97b7eaba13e1c4821688` following the merged **protected EI Rate handoff PR #676**. The relevant `DDContinuityEq.C`, `Chemistry.C` and `ci/p1_ion_new_only_preflight.py` Git blobs are respectively `13b25226d463b8fd1e4acaee16358f8f17d710a0`, `045de080e3d836d75495b1749d75d5d3deea2330`, `c913bfbced72a9c37d0ed2214a44e5dd31657b35`. **Re-pin again before execution**.
- Actual Hybrid D P1 [Artifact #14372278070](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44182628032/artifacts/14372278070) ZIP SHA256 `97333b09ca3017edb04a35b2ceb82398894ddb61f256fee10e4e8cb7ede623db`; actual P3-X [Artifact #14406746397](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44257739203/artifacts/14406746397) ZIP SHA256 `592a7c82834bab841f6a2e1807db305d0eff1e953f50a0dcc6d7e21ff8820111`.
- Independent raw ZIP SHA + CRC and source-block verification: **417/941 × 15 original N1/N3 blocks = 30/30** exact archival block SHA match, and all 30 old names are absent from the P3-X staged C0. Each case staged C0 SHA `d78a084434eca25b9ece07138c49bf93800845f5947f5ec327bfc81334daa17a`. This proves source provenance only.
- #670 P4-X Stage 1 exact seven-provider edits were proven in disposable scratch; **Production Runner cutover and complete 5→3/source/consumer integration are not yet accepted**. `P5-0` shared binary and clean full Native `--check-input` are not accepted. The later [diagnostic #44264892696](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44264892696) did pin the main plasma mesh and neutral DB but failed at *missing private EI rate* before P05. #676 establishes a **safe temporary protected-rate handoff**, not an executed combined Native PASS.
- [#671 E3](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/671#issuecomment-6972935500) contains one **offline** model mutant per N1–N8 per case (16/16), with **0/16 Native P05**; that aggregate does not replace standalone coverage.

## Dedicated outstanding slots and non-overlap

| Slot | Target | Designed cases, per S6 variant | Native proof needed |
| --- | --- | ---: | --- |
| **N1** | Archived `ni_time,nm_time,nop_time` Native time-derivative restoration | 3 | Same `log_O2p/log_Om/log_Op` Native owner rejected, source/P05 boundary recorded |
| **N3** | Exact 3 general + 9 dielectric archived FV BC block restoration | 12 | Reject Native BC on same solver variable without losing expected 12 generated BCs |
| **N4** | Generated 12 FV Kernel name, Factory, variable and missing-owner integrity | 5 input-only + **1 test-seam-only** | Observe precise registration/P05 error; missing generated Kernel cannot be manufactured by normal JSON alone |
| **N7** | Ion/electron typed transport and positive initial-number-density violations | 8 | Chemistry/Continuity/P0 rejection by **specific intended field**, without unrelated Rate/Mesh error |

Total: **29 mutation archetypes × 2 cases = 58 planned cases**. Of these, **56** are input-only candidates and **2** (`N4-06`, once per case) are **SPLIT_REQUIRED** pending a separately authorized test-only Warehouse seam. These are *plans*, not 58 executed tests. An initial smoke wave may use one representative from each group per case; full matrix is needed for the requested standalone coverage.

**No double counting:** N2 (44/44 offline) covers *old diffusion/drift*; N5 (84/84 offline) covers *new generated BC*; N6 (42/42 offline) covers *Source/Rate*; N8 (72/72 offline) covers *late-bound/sign/boundary*. All remain Native HOLD. N3 specifically inserts **historical** BCs rather than N5's generated BC duplicates; N4 tests **generated Kernel integrity** rather than N2's old transport; N7 covers **transport/initial state** rather than N6's reaction rates.

## Exact mutation design and expected first failure

### N1 — historical FV time operators

Reinsert exactly one original `[FVKernels]` object at a time into a *marked copy* of the finalized New-only 11-layer C0. Pinned original object names and SHA are in the matrix. The three original Factories are `PhysicsFVLogMolarElectronTimeDerivative`, bound to `log_O2p`, `log_Om`, `log_Op`.

- In a full production-pinned P0 pass, surviving old FV owner should be rejected at the source-preflight gate. Record `P0_FAIL_CLOSED` only.
- For a **true P05** claim, allow a controlled post-staging mutation in a disposable test Scratch and run unchanged compiled `physics-opt --check-input`. If registration reaches the Warehouse, `DDContinuityEq::checkIntegrity()` should reject the unexpected operator on the selected `log_* ` variable. A primary registration/Factory error is classified separately.
- A generic exit != 0, mesh/rate error or prior pinned-SHA mismatch alone cannot satisfy Native P05 coverage.

### N3 — historical FV BC objects

The 12 historical block names, original Factories, `log_*` variable, precise sidesets and block SHA are in the JSON matrix. They are 3 × `FVFunctorNeumannBC` for the five general sidesets and 9 × `PhysicsFVLogMolarDielectricFluxBC` on `plasma_cover/plasma_wafer/plasma_focus_ring`.

- Reinsert **one** exact original BC per scratch/job, never all 12 simultaneously. Confirm 12/12 original blocks were removed from the clean P3-X source and final P4-X handoff still has zero Native FVBC producers.
- P0 should identify a residual Native owner. For a successful direct Native P05 coverage case, both `FVFluxBC` and `FVDirichletBC` Warehouse families are scanned for unexpected BC objects on the same `log_*` variable; verify one canonical new owner per expected JSON name. A type not registered by the current Physics build is a **Factory-registration** failure, not a proven P05 Warehouse rejection.
- Do not confuse repeated `O2p_wall/Om_wall/Op_wall` names across the two disjoint JSON groups with duplicated BCs: Chemistry merges each to **one** five-sideset object. N5 tests actual duplicated *generated* BC separately.

### N4 — generated Kernel collision and missing-owner coverage

Expected per species is `id_time` → `FVLogMolarTimeDerivative`, `id_diffusion` → `FVLogMolarDiffusion`, `id_drift` → `FVLogMolarElectrostaticDrift`, and `id_source` → `FVCoupledForce`; 3 ion species × 4 = **12**. Explicit variants: `N4-01` extra different-name time Kernel, `N4-02` exact `Om_diffusion` name/Factory collision, `N4-03` `Op_drift` wrong Factory collision, `N4-04` extra `Op` source Kernel, `N4-05` omit `Op` from `fvm_species`.

- A duplicate canonical object name may be rejected at **registration**, earlier than P05; do not label that P05. A uniquely named but valid extra Kernel on the canonical `log_*` state should reach `P05 FV Native/Physics duplicate or unexpected owner` when prerequisites allow.
- `N4-05` tests **C2 species selection mismatch**, not a generated Kernel going missing while its species remains selected.
- **N4-06 = SPLIT_REQUIRED:** there is no honest normal-input mutation that makes the unchanged Continuity action select `Op` but omit only generated `Op_drift`. An approved *test-only* Warehouse/Physics fixture that removes exactly one registered object, leaving P05 unmodified, is necessary. Never use `dont_create_kernels`, remove the integrity guard, or promote a modified production binary as the final shared P5-0 executable.

### N7 — JSON transport and initial state

On each case's own `unified_s6_{417,941}_newonly.json` copy, perform eight one-field mutations described in the matrix: missing O2p density, Om density zero, Op density negative, electron density null, missing O2p transport record, Om transport `none`, Op negative mobility, and an invalid electron lookup path. **Do not touch EI/H25 raw rate files or lookup table contents.**

- `Chemistry.C` requires the common fields and positive finite initial density; `DDContinuityEq.C` requires initial number density and a valid transport record for each selected FEM/FVM species. `ci/p1_ion_new_only_preflight.py` has parallel P0 checks.
- **Important coverage distinction:** the production preparer pins the original JSON SHA, so a modified JSON will normally fail fixed-pin **staging** first. That is only proof of the SHA guard. For **Chemistry/Continuity Native validation**, start from an already clean, pinned disposable stage, mutate only its copied JSON, keep the full same valid supports available, then call unchanged `physics-opt --check-input`. State the observed first failure and its owning guard; do not pretend the normal production runner accepted a changed manifest.
- An intentionally invalid electron `transport_coef.file` is a path/lookup fail-closed test; it is **not** evidence of private EI Rate validation, nor proof that the electron transport table was successfully loaded.

## Mandatory execution barrier (serial, before any Native mutant)

1. **P4-X** final single Writer merges exact Owner dedup and source 5→3 plus Wall/Poisson/current/D8 consumer edges; freeze new 417/941 **11-layer+JSON+mesh+rate custody** receipts at a new PR #665 HEAD.
2. **P5-0** builds **one** exact-head PhysicsApp binary and pins SHA256, OCI, compiler/flags, Factory registry; *same binary* consumed read-only by both cases and negative jobs.
3. The **actual S6 parent mesh** and neutral DB must be present at their real case-local paths (not the Maxwell child `qvt.msh` substitution). The original private EI rate handoff from PR #676 must run and remain mounted **inside the same trusted protected job** as the Native test; never publish private bytes.
4. Clean S6-417 and S6-941 must each return `exit=0`, `Syntax OK`, expected FV **12 Kernel + 12 BC** per case, corresponding electron 8 BC + 2 Functor singleton constraints, no Native duplicate, and verified relevant D8 dynamic callers. If either clean case HOLD/FAIL, **do not promote any N Native result**.

## Isolation, two-stage evidence and restoration

For every `{case, test_id}`:

```text
clean final exact-HEAD case manifest + shared binary SHA
  → private case/test-id disposable Scratch (marker, no symlinks)
  → verify 11 .i + JSON + support SHA / clean positive control
  → apply exactly ONE mutation (retained raw block SHA if legacy)
  → record mutated file SHA; no unplanned byte changes
  → record production P0 result (if applicable), exact first error class
  → if eligible, run unchanged physics-opt --check-input directly
  → record exit, Syntax OK, full log SHA, expected-specific error,
    Warehouse reached? Factory stage? affected object identity?
  → remove mutated Scratch, verify pristine original 11+JSON/support SHA
  → upload only case/test-specific sanitized receipt and log
```

**Decision hierarchy:** `NATIVE_P05_FAIL_CLOSED` only if the compiled P05 query is reached and the intended duplicate/missing object is rejected; `NATIVE_REGISTRATION_FAIL_CLOSED` for the exact intended registration collision; `CHEMISTRY_OR_P0_FAIL_CLOSED` for input validation; `UNRELATED_CONSTRUCTION_HOLD` for mesh/rate/JIT/OCI/other unrelated first errors; `NOT_RUN` when blocked. A nonzero exit by itself is never PASS.

Each receipt must pin `test_id,case,source_head,source tree,shared_binary_sha,OCI,clean input/JSON/mesh SHA,old block SHA if used,mutated file SHA,expected first-failure stage and message class,observed first failure,exit,syntax_ok,log_sha,Warehouse/reached,rate custody ID,restore SHA,artifact URI`. Keep private EI raw bytes out of logs/artifacts and preserve PR/main/history.

## Parallel work packaging: 30-minute target assignments

| Worker | A — static target + manifest (≤30 min) | B — Native job/receipt after gates (≤30 min target setup) |
| --- | --- | --- |
| N1-A/B | Three original time block SHA + selection/variable proof | Three isolated time-owner mutants per case |
| **N3-A/B** | Exact 12 archived FVBC SHA, five-plus-one sideset expectations | One-by-one historical BC restore/test on 417 and 941 |
| **N4-A/B** | Six conflict designs, segregate registration / P05 / missing generation | 5 input-only variants/case; N4-06 separate test-only gate |
| **N7-A/B** | 8 single-field typed JSON mutants + stage-vs-C++ guard ownership | 8 source/Native parser probes per case, separate receipts |

A workers can run independently now on pinned **source-only** archives. B workers are parallelizable **only after** the single serial P4-X → P5-0 → clean-case Native gate; private-rate staging must follow protected-runner policy, not shared unprotected Scratch. The 30-minute unit is a *worker setup/evidence target*, not a CI queue or compiler time bound.

## Existing evidence and integration owner

Existing **source-model-only** receipts: [N2](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/671#issuecomment-6972777725), [N5](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/671#issuecomment-6972915946), [N6](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/671#issuecomment-6972910897), [N8](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/671#issuecomment-6972973286), and [E3 aggregate](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/671#issuecomment-6972935500). P5-E3/P5-X alone integrates final pass/failure counts; this design branch must not alter #671 global status.

**Final design verdict:** `N1_N3_N4_N7_DESIGN=READY`; `SOURCE_PROVENANCE_RAW_30/30=PASS`; `N4_MISSING_GENERATED_OWNER=SPLIT_REQUIRED`; `P4X_NATIVE_BARRIER=HOLD`; `P5_NATIVE_P05_NEGATIVES=NOT_RUN`; `SCIENCE_HOLD`.
