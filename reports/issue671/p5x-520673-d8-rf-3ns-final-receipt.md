# P5-X D8 same-W1 RF-on 3 ns revalidation

Date: 2026-11-18. Checked immutable PR #665 source HEAD: 52067302d16074592503d0ef6b903cc344f55a08
Build tree: 2720fa5272a5fa98001e8e444331397723fe7ccb.
Later PR #665 HEAD at receipt write: 3b447b67283dac3b1d5e592ed3db6e56754c3d0e. The result belongs to 52067302 only; latest-head strict gate is HOLD after advancement.

## Actual execution and identity

- Single 52067302 W1 Build: https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44345886330 ; artifact 14446611291; zip SHA256 6d24d997075c76983b5d99fc28c3cfc0f9fae1a57ccc00c63af4d8697c83d676.
- Same W1 ELF SHA256: 912b212c3c1849165ab3da13d758f5b3e101f5b6cb7e1e3f3820259f6080f7eb; app libs: 61f66ec66843f1d51bd79ef7542197410bebf92487f2cff70e9e08f9e958da82 and e9ad1adeb8fcba312cf836520927a3de3fc5ad986d35d50f6cfe5d114e825f0f.
- D8 exact-W1 actual Run: https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44350479243 ; job 134964417690; workflow commit 894e779a01fd6b57cff25490f69ea98ee9ec47a8; completed SUCCESS.
- D8 artifact 14448238106, zip SHA256 54d50a3f18336c3b95300f3adc0ff72d19cebfa19e38fffdc32dd2e040188248, CRC PASS. Reused W1 ELF bytes, build identity JSON byte-identical; no recompile.

## Actual 417 and 941 RF-on same-run evidence

| Metric | S6-417 | S6-941 |
|---|---:|---:|
| Native check-input and RF 3 ns | exit 0 / exit 0 | exit 0 / exit 0 |
| Child Maxwell P_abs, W | 209.31596771096 | 209.31597896021 |
| Parent received P_abs, W | 209.31596771096 | 209.31597896021 |
| Seven original Transfers | PASS 7/7 | PASS 7/7 |
| D8 finite postprocessors | 34/34 | 34/34 |
| Number-to-mass conversions (3 sides x 3 ions) | 9/9 | 9/9 |
| Surface current species charge sum (3 sides) | 3/3 | 3/3 |
| Poisson charge and source unit/sign | PASS | PASS |
| Cover integrated surface current, A | -3.6011286276022 | -3.601129411267 |
| Wafer integrated surface current, A | -0.85181504110183 | -0.85181503581399 |
| Focus-ring integrated surface current, A | -0.057864287198826 | -0.05786428553962 |
| Poisson charge integral, C | 6.0425364377895e-8 | 6.0425366778037e-8 |
| Poisson source integral | 6824.4954427714 | 6824.4957138455 |
| Cover assembled residual L2 | 9.1846843204073e-16 | 8.7363940423421e-16 |
| Wafer assembled residual L2 | 3.5271378638386e-16 | 4.0706863356423e-16 |
| Focus-ring assembled residual L2 | 2.6969266635746e-16 | 9.2090178756206e-17 |
| Poisson assembled residual L2 | 5.4486428053723e-11 | 5.3612688903395e-11 |

Three physical 1 ns steps, original RF TimeSequenceStepper and Maxwell child, 11 original input layers per case, protected EI rates 5/case, protected scratch cleanup PASS. Actual 417 and 941 34/34 numbers exactly equal to older same-source W1 74a Run 44346835225, artifact 14445594805 (zip SHA256 a1f37b29ffb6095b329631cead8f8ae5b30f97c95d1697345f9dc58ec2728c73).

## Independent audit and acceptance limits

Three actual GitHub artifact ZIPs rehashed; ZIP CRC, W1 ZIP/TAR/three ELF member hashes, exact source identity, 417/941 34 numeric observables, 7 Transfers, flux mass conversions, current sum, Poisson charge/sign/units, four assembled residuals, secure cleanup: 187/187 PASS.
Verifier script SHA256 5a742cec9400c4757057acef6baee846712b1cfcf96f18f657f27554b454db04; verifier result JSON SHA256 b52eac1d30d719b33f1008f21f3ff906a39904ded5568449a686a243a0a0164b.

Verdicts: D8_EXACT_520_RF_WALL_CURRENT_POISSON_3NS=PASS_BOTH; P5_X_BOUNDED_DYNAMIC_520=PASS; SCIENCE_HOLD; NATIVE_P3_P4_100US=NOT_RUN; HISTORICAL_HYBRID=KEEP_HOLD.
These are assembled variable residual L2 values, not direct kernel computeQpResidual function-entry traces. Raw full stdout and full CSV not published. Three-ns reproducibility does not establish 100-us scientific equivalence.
PR #665, main, PhysicsApp, P05 guard, original public S6 sources and original protected rate bytes were not modified by this test.

Exact-head caveat: PR #665 advanced after this run; current PR #665 cannot inherit an exact-head PASS from the 520 W1. The later 1-commit diff affects workflow, CI guard, and tests only, with no PhysicsApp file changes, but strict source HEAD identity remains separate.
