# Issue #668 P2 — pinned static retirement replay

**Result:** `P2_STATIC_DISPOSABLE_26_TO_0=PASS` for both S6-417 and S6-941. This is a source-only local Scratch replay, **not** a new GitHub Actions/Native P2 run.

## Immutable inputs and exact code

- Draft PR #665 frozen HEAD: `9c15a4f0e2cf8042cb0d4b2f18af31511021d168`.
- P1-0 exact source artifact [#14372278070](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44182628032/artifacts/14372278070), SHA-256 `97333b09ca3017edb04a35b2ceb82398894ddb61f256fee10e4e8cb7ede623db`; internal `common_manifest.json` SHA `14a8eb65dc00e424efdce2ab6f8a44a8bf4447f95500a9bfbb01bf403667e010`.
- Independent equivalent exact input artifact [#14372278074](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44182663514/artifacts/14372278074), SHA-256 `584fd8eff989ab1f7f0a7582ae72b4dc2429f84b8b05ed91c1a46f89df88da5e`. Exact 22/22 staged `.i` file bytes equal to #14372278070.
- Exact prepatch `retire_s6_ion_fv_owners.py` Git blob `e4866dfd68fcb54f21c2bbaa303b79dde87b4c81`. Guarded source in this branch Git blob `41219d43c63aa2c6db025a48831ccc9a6493190e`.
- P1-E source owner census [inventory](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/a3e22628d863c3b2f06ba34b2050a6ae99a7c699/reports/issue667/p1-e/inventory.json).

## Reproduce without Native execution

1. Download the P1-0 artifact ZIP through the provided Actions link and verify its whole ZIP SHA-256. Extract `cases/417/case_manifest.json`, `cases/941/case_manifest.json`, and their `final_11_inputs/*.i` files.
2. For each case, create a **new** disposable Scratch directory and copy exactly 11 real `.i` layers into it; put plain regular file `.issue633_disposable_scratch` containing `issue633-scratch-only`. Pass an `ordered.json` built from the case manifest `ordered_input_paths`.
3. Use this branch's `retire_s6_ion_fv_owners.py` in CLI mode with `--staged-chem-dir <scratch>`, `--ordered-file <ordered.json>`, `--case-manifest <case_manifest.json>`, `--expected-source-head 9c15a4f0e2cf8042cb0d4b2f18af31511021d168`, `--receipt <output.json>`.
4. Confirm each case has 14 removed FVKernels + 12 removed FVBCs, exactly zero residual native ion FV owners, 26 old block SHA matches, five changed files, six unchanged files, all other bytes preserved. Test tampered head, input file, block, factory, missing owner, duplicate, symlink and marker; verify no unexpected writes.

The original unpinned retire helper accepted altered `O2p_diffusivity` `coeff` while retaining the correct 26-owner count. This branch enforces **all 11 exact file hashes and all 26 exact owner block hashes** before any write, failing closed on tampering. The local audit executed 16 distinct negative mutations per case, all **32/32 rejected without file mutation**.

## Evidence and remaining gates

The consolidated [receipt](./p2_static_retirement_integrated_receipt.json) contains **22 before/after file hashes**, **52 old object block hashes**, and the explicit 32 negative controls.

**Not claimed:** production `prepare_s6_run_input.py` runner hook remains unwired, New-only JSON/11th-overlay handoff remains unverified, Maxwell current wrapper differs from historical bytes, D8 New-only dynamic callers HOLD, actual Physics-generated 24 Native owners NOT_RUN, Native P2/P3/P4 NOT_RUN, SCIENCE_HOLD. The P2 package DoD and P3-X activation therefore remain gated.

No private EI rate bytes were read or published in this P2 replay.
