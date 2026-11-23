# #774 D10 — exact-HEAD New-only W1 + Native 417/941 P05 requalification

> **D10 actual Native: PASS, exact-B input/registration comparison 44/44 PASS.** Old current-binary input support was explicitly waived. This is P05 construction and registered-object parity, **not** 100 µs physical equivalence or whole-Warehouse caller closure.

## Exact immutable provenance

- Tested [Draft #795](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/795) at `05a3cf85bc5ed7d9c258b1377bd66d68d70f4e3e`; source tree `51d9fcd765e0db3006f29b2775d19f118c26aeab`.
- Relative to D9 source head `87b7d97113ce6e75081dd15c56c86bc159bde6c9`, the **only** file added is `.github/workflows/issue774-d10-newonly-native-once.yml`. No Physics C++/Header, mesh, chemistry JSON, canonical `.github/workflows/ci.yml`, template, nor Poisson source change.
- Exact [run #45199787795](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45199787795): W1 **PASS** / protected 417+941 Native P05 **PASS**.
- W1 Artifact **#14832500622** ZIP SHA256 `c3fbf30f473625e8238a938f5dc5b8d82c37ddbc7d789dd994ef92bde88e07d9`. Native sanitized Artifact **#14831463422** ZIP SHA256 `5413450bd9d30a4633919abe62b40c3dbb14a2f5630053a32b42c490c833f2ff`.
- Exactly one built ELF `6afd05d4a4d356fe5132ca28076ba27e06bea93d485ac8a6b39d334bb9a9465b`, two pinned app libs `c7471a17e934d13bf335016da8839414e6f518444c05b0d95648714151724044` and `107e9f56458958bfcf6385ea0d79651a96675d5f724d1f8e40b591ca729a1ec5`, container `physics-build-base@sha256:2c3352da...`. Tar member roundtrip and W1-to-P05 same-binary identities verified. No private data in Artifacts; tmpfs cleanup verified.

## Actual Native source/type and input parity

| Fact | 417 | 941 |
|---|---:|---:|
| Clean input syntax/exit | PASS, rc 0 | PASS, rc 0 |
| Exact public source layers | 11 | 11 |
| FVKernel events | 40 | 40 |
| FVBC events | 21 | 21 |
| FE BoundaryCondition events | 16 | 16 |
| All Native registration events | **77** | **77** |
| Observer preload markers | 323 | 309 |
| Old `PhysicsFVThermalDiffusion` observed | **0** | **0** |
| Native N1–N8 negative checks | Total **16/16** | For both cases |

Actual source use in **each** case: `FVLogMolarTransport.C` 9, ConservativeMassFractionTimeDerivative 3, MassFractionAdvection 3, MixtureAveragedDiffusion 3, SpeciesReactionSource 6. The seven other local FVKernel sources have zero observed registrations on this selected P05 route. All 12 source Blob/Factory ownership rows remain equal to the prior B Native run.

Independent parsed receipt comparator versus original [B #783 run #45177755891](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45177755891) checks **44/44 conditions PASS**. Crucially, **417/941 public 11-layer SHA lists, chemistry JSON SHA, mesh SHA, actual type distributions, event family counts, source row identities, 16/16 negatives, cleanup and build/source/ELF chain match**. The two different source commits have their own exact ELF identities; bitwise identical ELFs were not required because C++ source did not change.

Comparator report SHA256: `e453553738bd516bb5210682e1a8750963c07949ebfb79b4d01711963844e627`. The full public comparator JSON is available as the linked conversation artifact; this PR stores its SHA and machine-readable results without importing generated private input.

## Generated-input/external consumer scope

Within these actual **417/941 supported Native P05 routes**, every runtime FVKernel add call observed by the `FEProblemBase` post-original-call tracer is recorded, with input source-layer hashes. No old thermal class registered. **This is much stronger than a static `grep`, but is not a claim that all generated inputs or external consumers have been exercised.** Other generators, unselected experiment configurations, future inputs or third-party integrations are not independently attested.

The user's [legacy-support waiver](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/774#issuecomment-7103483022) removes the *old typed input compatibility gate*, but not source/CI safety, current New-only runtime, independent review or rollback.

Historical FDEG CI D8 [#791](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/791) separately passed **99 FDEG P0 tests**. Actual New-only CI D9 [#793](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/793) separately passed **15 P0 tests**. D10 now closes **exact new SHA W1 + both selected Native P05**. Do not transplant the legacy FDEG Workflow into New-only, and do not merge this one-off D10 test Workflow to production.

## Remaining formal gates

- **Independent dynamic/generated/outside-repository consumer review** beyond these selected Native P05 cases.
- **Final reviewed combined integration HEAD**, including Poisson when authorized, must be requalified; D10 is an isolated Draft, not `main`.
- **Rollback and independent owner review**, no fabricated external approval. Original FDEG evidence ZIP retained on historical branch.
- **P3/P4 and 100 µs full time integration**, including physical conservation/semantic compatibility, remain `SCIENCE_HOLD`.

**Result: `D10_NATIVE_P05_PASS / D5_B_TO_D10_44_44_PARITY_PASS / EXTERNAL_SCOPE=HOLD / SAFE_DELETE=HOLD / MAIN_MERGE=DEFERRED`.** [Machine receipt](newonly_d10_exact_head_native_p05_v0_1.json).