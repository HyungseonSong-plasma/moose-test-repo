# P6-D5 — Public D original 100-row latest Physics Native P2 + P05 typed Owner acceptance

**Status:** `PASS_CONSTRUCTION_ONLY` for Public D S6-417 and S6-941. **Not P6-X full-CI PASS or science acceptance.**

## Mode/Source custody

- Physical production source: `3b447b67283dac3b1d5e592ed3db6e56754c3d0e` (Draft [#665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) prior exact source head). Current #665 observed `fd21e2e31c48d0fa495f0830b52a70fb06815514`: two newer commits change only six `.github/workflows/ci.yml`, `ci/guards/*`, `ci/workflow_templates/general-ci.yml`, `tests/test_issue672_p6_ci_workflow_safety.py` paths; no PhysicsApp, Chemistry, source stager, or original Lookup file changed. Do not call the old ELF an exact `fd21e2...` executable.
- Original `Issue91/r3_e0/electron_moments.txt`: **100 rows**, SHA-256 `994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387`; source Git Blob `bedcaf17fb3ef93ba8973cc6b32aa6e783e2292a`.
- Prepared 42-row model SHA-256 `35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b` is distinct and never substituted for actual Public D's 100-row Lookup.
- Disposable 11-layer 417/941 cases use the real seven-species / eight-reaction Chemistry; 26 legacy ion FV owners retired; no protected original source modified. The original 100-row staging receipt bytes (GitHub artifact members) **match exactly** across the two independent Native runs.

## Real Native P2 (separate source-bound pilot)

[GitHub Actions #44354230639](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44354230639), [Artifact #14453620080](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44354230639/artifacts/14453620080), ZIP SHA-256 `9ebea15f02fc1e4e21d8ab8d395480addebaad28df67769685369a493e4cee9c` (independent CRC/SHA audit PASS).

| Case | 100-row real Native `--check-input` | Log SHA-256 |
| --- | --- | --- |
| 417 | Exit 0, Syntax OK | `4a94735008ba772e4c5ad2165e9611619be8cecd6081eaa5103d8959144c8a90` |
| 941 | Exit 0, Syntax OK | `e2718a67b6f2237cc68fc1c3863ccb39d6d9ce60e3e627c5fe6c3c27520d5851` |

Both under the same job-local ELF SHA-256 `35aba69374914309857e291694f54762e558cd2ad991498396070dc1a8555467`; two app library SHA recorded in machine receipt. This run itself did **not** directly meter typed Warehouse registrations.

## Independent P05 typed/16-negative Native on single fixed ELF

[GitHub Actions #44357169166](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44357169166) **SUCCESS**, [Artifact #14451778372](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44357169166/artifacts/14451778372), ZIP SHA-256 `f6b295c99d34177228dd0989251612afa23c07644e9d990a4a3c84e37948cc5f` (independent ZIP CRC, per-member and receipt verification PASS).

- Fixed W1 [Artifact #14449097760](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44352827068/artifacts/14449097760), source `3b447b67...`. ZIP `84ce92ead209f458042977452a9284b78cac224c9adadc7b74015568474fcb7e`; ELF `efab43df773398d0c1f6eadf5bc384fbb325da10e67a5c21571039fec6dadcc6`; apps `141c951d6887eea44694324c70f48add2d6fd8e31285327196b5aa49f48f6b41` and `80cc6690292a4c26064756be14ab0d82aea2c53f85f60c16546c871af1f6568f`. **No PhysicsApp rebuild for this P05 run.**
- Real `FEProblemBase::addFVKernel/addFVBC/addBoundaryCondition` post-call interception in the pinned OCI, in addition to the unmodified production `DDContinuityEq::checkIntegrity()`/P05 path. Registration events: **77 per case**; inspected expected typed/factory/name inventory: **12 FV Kernel + 12 FV BC + 8 Electron FEM BC = 32/32 per case**, 64/64 total. No unintended generated/native duplicate.
- Actual clean 417/941 Native `--check-input`: **both Exit 0, Syntax OK** with the same fixed W1 ELF.
- Each case Native negative controls `N1–N8`: **8/8 actual exit 1 with expected first error**; combined **16/16**. `N1–N4=P05`, `N5=EARLY_REGISTRATION`, `N6–N8=CHEMISTRY`.
- Exact original 100-row staging JSON SHA for both independent runs: 417 `22683fcfe76c800fe1041212f818fe3aecf77105d66b059b5a46ab273212e2ed`; 941 `9b08f33cd9db3c7a5dd9c5ee7a19d03397a13fb408987768bfac51aebc3d8bda`.
- Protected EI input confined to per-case `/dev/shm` then deleted; protected raw data not uploaded. No automated P3/P4 or time-stepping.

## Acceptance boundary and onward handoff

```text
PUBLIC_D_ORIGINAL100_NATIVE_P2 = PASS_417_AND_941
PUBLIC_D_ORIGINAL100_TYPED_P05 = PASS_32_OF_32_EACH
PUBLIC_D_P05_N1_N8 = PASS_16_OF_16
PUBLIC_D_P2_P05_ACCEPTANCE = PASS_CONSTRUCTION_ONLY
DIRECT_THEWAREHOUSE_MEMORY_DUMP = NOT_CAPTURED
SCIENTIFIC_NUMERICAL_EQUIVALENCE_100_VS_42 = NOT_CLAIMED
FLOW_HYBRID = KEEP_HOLD
ARCH_HYBRID = KEEP_HOLD
P6_X_FULL_REPOSITORY_CI = SEPARATE_HOLD
P7_FINAL = HOLD
NATIVE_P3_P4 = NOT_RUN
SCIENCE_HOLD = TRUE
MAIN_PR665_MERGE = NOT_AUTHORIZED
```

This is suitable for P6-X evidence integration, but P6-X must separately decide CI Lane ownership and final workflow failure disposition. It is **not** permission to convert historical Hybrid failures into success, or to promote bounded P2 to P3/P4 science.

**Machine receipt:** [p6d5-public-d-original100-native-p2-typed-p05-20261118.json](./p6d5-public-d-original100-native-p2-typed-p05-20261118.json).
