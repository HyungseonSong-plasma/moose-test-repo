# #774 D11 — actual Public D 100-row generated inputs and New-only B rollback custody

> **D11 tested scope PASS, no current-binary legacy input obligation.** The actual 417/941 Public D generator ran on SHA-pinned public layers. Neither Native Public D P2 nor 100 µs P3/P4 science was run. No outside-repo consumer-zero, approval or production revert is asserted.

## Source and proof

- Tested [code-only Draft #798](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/798), exact HEAD `6c4b99b5798fa6636fa3d13e1edaefe3bd601612`, Git tree `f37f3a70f18a744a824e3913676d43d0432f38de`, based on exact green D10 #795 `05a3cf85bc5ed7d9c258b1377bd66d68d70f4e3e`.
- Actual [run #45206089662](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45206089662) **SUCCESS**; sanitized Artifact **#14833158719**, ZIP SHA-256 `54944466ef404369dfadf9ecba4217179f6701f5b0510edbe852077ef4cc11cd`.
- Source replay: D10's original public 400-W parent mesh, exact P3-X 11-layer stage, P4-X seven duplicate-owner preflight/cutover, and **real** `experiments/Issue402_plasma_dsl_g1/chemistry/prepare_public_d_newphysics_100row.py:stage_public_d_physics()` in **two isolated scratch copies**.
- No W1 rebuild or protected EI-rate acquisition. Generated input bytes and mechanism JSON were parsed after writing, not merely inferred from static source.

## Real Public D generated output

| Observation | S6-417 | S6-941 |
|---|---:|---:|
| Output input layers read back | 11 | 11 |
| MOOSE `type =` statements in rendered inputs | 320 | 321 |
| Distinct input type names | 56 | 56 |
| Distinct generated chemistry JSON `type` values | 7 | 7 |
| `PhysicsFVThermalDiffusion` occurrences in output | **0** | **0** |
| Synthetic generated Chemistry name | `public_d_s6_417_physics.json` | `public_d_s6_941_physics.json` |
| Generated overlay SHA256 | `26d8f93ad9fe3fbe002899b112b595764e437cfefdc6a7ffbd67258f6ebb41d9` | `97b2bf1225a2e05cf35c8a4ad9644e858a439221908625e0fa2981ea749127c1` |
| Original source inputs modified | No | No |

The original **100-row** public electron transport source remained SHA-256 `994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387`, and each case's 42-row staged table was copied into an isolated workspace before the generator replaced it. Output layer and chemistry readback matched the generator's own receipts. 6 explicit P0 regression tests reject old type introduced through either `.i` or dynamic JSON, wrong 11-layer count, unexpected bytes and incorrect rollback SHA, while preserving the independent `QPXFVThermalDiffusion` class identity.

This closes the **generated input source scan** for these two Public D 100-row routes; it does not establish that the resulting inputs construct or converge under a Native PhysicsApp binary. D10's Native P05 used the **different existing 42-row New-only route**.

## Rollback custody: SHA-pinned, not executed

- Archived, **post-source-removal New-only B** source: `c77d2f773eee96c30eeca49d7486fea22ea8e557` (D5 B #783).
- Current D11 `HEAD:physics_app` and B `HEAD:physics_app` both have Git tree SHA `42d40ba2be12c08da23fa6f4ac8d8d496fe8aaa1`. So all PhysicsApp tracked source bytes agree, not only the two Thermal filenames.
- The original B W1 run #45177755891 was re-downloaded and checked: one build, pinned OCI, archived tar SHA-256 `37104cdcae3d7009445258302b1008e0af416e2301d78d4b21c47246bbe2ba43`, **all three ELF/application-library tar member byte digests verified**. Original B `physics-opt` ELF SHA-256 `d6a87b61f7e3e8d06767f7a245c51e846293af740653609492d2e3f9714ac62c`.
- Corresponding old B Native P05 receipt independently verified `PASS_16_INTENDED_NATIVE_REJECTIONS`, 16/16 negatives, 417/941 clean syntax/exit, no private artifact, and successful private tmpfs cleanup.
- **No revert was applied to `main`** or deployment, no legacy Thermal Factory was restored, no P3/P4 replay; this is archival **rollback readiness**, not a production rollback acceptance test.

## Remaining consumer-review matrix

| Route | Current evidence | Disposition |
|---|---|---|
| New-only 42-row S6-417/941 | D10 exact-head W1 + Native 77 registrations/case, 44/44 comparison with B | PASS for instrumented P05 |
| Public D 100-row S6-417/941 | D11 actual rendered 11-layer and mechanism JSON, old type 0 | PASS generator output only; Native P2 not run |
| Historical FDEG code7 | D8 archive Graph and 99 P0 tests | HISTORICAL ARCHIVE; not New-only active Factory |
| Other supported generator variants | Not executed and not independently classified | HOLD / owner to enumerate active entrypoints |
| Outside-repository consumers | Not inventoried by these source runs | HOLD / independent owner attestation |
| Scientific full 100 µs / P3/P4 | Not run | SCIENCE_HOLD |
| Production merge/revert | Main untouched, Poisson untouched | DEFERRED |

The user's old input compatibility waiver ([#774](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/774#issuecomment-7103483022)) remains valid. Do **not** silently treat it as permission to skip CI, to drop archived evidence, or to claim independent external closure.

**`D11_PUBLIC_D_GENERATION=PASS_417_941 / B_SOURCE_ELF_CUSTODY=PASS / ROLLBACK_EXECUTED=FALSE / EXTERNAL_SCOPE=HOLD / SAFE_DELETE=HOLD / MAIN_MERGE=DEFERRED`.** [Machine receipt](newonly_d11_public_d_rollback_v0_1.json).