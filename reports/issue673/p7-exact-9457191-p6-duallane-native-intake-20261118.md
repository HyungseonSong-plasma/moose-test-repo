# P6-X / P7 evidence intake — exact #665 HEAD 9457191 (2026-11-18)

**Source**: Draft [PR #665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) at `9457191f4c0693ae886586edd961965867ccd5c0`, unmerged to main. Merged [#689](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/689) Public D original100 source and [#690](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/690) mandatory Public D CI. This is an **independent receipt branch**; no feature-branch mutation.

**Authoritative [Repository CI #44366325757](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325757)**: `completed/success` **20/20 jobs**, run_attempt 1, exactly matching PR HEAD. Required `p6_newonly_s6_native_p2` and `p6_public_d_100row_native_p2` **both SUCCESS** using one [W1 build Artifact #14458195502](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325757/artifacts/14458195502). Build ZIP SHA `d0b83a2cde6bea28546399236494392e3317cda7eeedeb5a71aa30f975ed7bef`. ELF `b327aea7f496809779dd233336d8c62d15ab021accdb13e552efe1a750c72e18`; two app libs `59f09eb9d88b42d5932bad848a7b3ff33faebfb843b3790247d868aea28abbee` and `31abf727e4a40d7e2d91a6ba45d26f9d7b682cde198cf4d43188609c53e33db8` (original byte SHA verified).

| Native scope | New-only 417/941 | Public D original100 417/941 |
|---|---|---|
| Clean real `--check-input` | 2/2 PASS | 2/2 PASS |
| Post-add typed registrations per case | 12 FVKernel + 12 FVBC + 8 e FEM BC | 12 FVKernel + 12 FVBC + 8 e FEM BC |
| N1–N8 actual Native negatives | 16/16 intended rejections | 16/16 intended rejections |
| First-failure categories (both cases) | 8 P05, 2 early registration, 6 Chemistry | 8 P05, 2 early registration, 6 Chemistry |
| Private rate scratch and original source SHA restoration | PASS | PASS |
| Sanitized receipt | [Artifact #14458752206](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325757/artifacts/14458752206) | [Artifact #14459116868](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325757/artifacts/14459116868) |

**Independent original ZIP audit**: 385/385 actual ZIP/TAR/ELF/Receipt checks PASS; source script SHA `e82c0b8e1403e08f8f21dd7da9c238595e70a0171a46b0b498bec379088c1c4c`; audit JSON SHA `69f3905dd97781668269a60ce6eda62f7c4aeab03da53e33b8c077811e60ef5f`. The audit does not rerun PhysicsApp or directly inspect live warehouse memory.

**Mode boundaries**: Original Public D 100×3 Lookup SHA `994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387` retained in disposable Scratch; no historical D P2-only runner. Historical Public B PASS control and historical Public D expected rejection `KEEP_HOLD` remain in separate legacy job; not a contradiction with new positive generated-Physics Public D. ARCH Hybrid `KEEP_HOLD` after P05 `ni_time`, FLOW Hybrid `KEEP_HOLD` with [standalone FAILURE #44366325812](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325812); old Ion-FVM `KEEP_HOLD_PRE_NATIVE`.

**Verdicts**: `P6_X_CI_EXACT_945=PASS_SCOPED_P2_WITH_HISTORY_HOLD`, `P7_P2_CI_INTAKE=PASS`, **`P7_FINAL=HOLD`**. The previous D8 RF/Wall/Poisson 3 ns PASS is pinned to older `52067302…` W1 and is **not** an exact-current-945 ELF D8 check; `D8_EXACT_CURRENT_HEAD=HOLD`. P3/P4 100 µs = `NOT_RUN`, `SCIENCE_HOLD`. No authorization for main merge, P05 bypass, archive edits, or scientific equivalence.
