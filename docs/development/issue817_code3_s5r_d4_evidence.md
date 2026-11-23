# Code3 #817 D4 — normalized S5-R source and bounded current-binary evidence

**Canonical issue:** #817; parent #774. **Stack:** clean Draft #819 → Draft #820. Base for #820: `issue-817-code3-consumer-pair-d3@97ecf94e7f4749602857942ce7b99c0ef43de1ba`. Existing `PhysicsFVElectronReactionSource.C/.h` and its Factory registration are **intentionally retained** (C blob `35ded0eab65ad7bed85baa0104261c90bc26bf3d`, H blob `5250b3500d6694481158e2abb896c7e1c6f349e9`). No production Physics input, generator, or canonical CI modified.

## P0 source ledger and negative controls — PASS
[Run #45237261983](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45237261983) terminal SUCCESS at `c5cc9efee321891c52763c3516191dd77306d939`; all 5 signed source/normalization/EI18/EI19 negative tests PASS. `S_e_s5r` is the single physical electron-number source; source Functors are EI01, EI16, EI20, EDETACH and H05. EI18/EI19 must remain energy-only. `coef = 1/n_ref > 0`; other input bytes outside the one electron Kernel block unchanged. Artifact #14848534210 SHA256 `8bfd9857dee1a7136f2ed43674abf440b22fd872a51d56df55e63a1aa1756908`. The earlier P0 AST quotation parser failure #45236785139 was fixed using `mp.unquote`; original Physics code unchanged.

## Historical/legacy full S5-R current New-only P2 — FAIL for both arms, independent Thermal owner
[Initial Native #45237434118](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45237434118) failed the exact original and candidate P2 after clean PhysicsApp W1. Artifact #14849852657: both return code 1 / Syntax OK false. Diagnostic [retry #45238738588](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45238738588) at `65f1f0496cdaa79d48a54c32f28ccf53212b1560` likewise failed *both*, with identical first MOOSE error:

`A 'PhysicsThermalDiffusionMaterial' is not a registered object.`

The source P2 receipt Artifact #14850683720 SHA256 `eb72fb891b305ef556bc514b38d396ece38899f6b17dad28ba94428aee35ff5f` directly confirms both error contexts, paired source/input SHA, exact new ELF SHA and `safe_delete=false`. The current New-only build does not support this historical/representative S5-R material. **Do not treat this as Code3 replacement-specific failure, nor as permission to waive live S5-R CI without separate scope/owner decision.** Full S5-R P3 is NOT RUN, coupled AD Jacobian NOT VERIFIED.

## Isolated current-binary normalized nonlinear source control — PASS, bounded
Exact W1 + Native [run #45239977824](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45239977824) terminal SUCCESS at `395f532d882e9f3cd79f721ebfc4ce3c72f44586`. Pinned OCI source/build, ELF SHA256 `9f58cb7c929a20b9ad277c20394ea8a680e36e1fc6d3f94a22a9d3cfabf303b4`. Artificial one-cell `S_e_s5r=sign*n_ref*(0.4+0.1*n_e_hat)`, `n_ref=1.298e18`, positive and negative source directions; old Code3 vs standard `FVCoupledForce(v=S_e_s5r,coef=1/n_ref)`, identical non-target input. For each sign: all original, replacement, and **flipped-coefficient control** P2 Syntax OK and one-step P3 ran successfully.

| Signed source | Old final n_e_hat | Standard final n_e_hat | Wrong-sign coefficient | Analytic implicit-Euler |
|---|---:|---:|---:|---:|
| production (+) | 1.0505050505051 | 1.0505050505051 | 0.95049504950495 | 1.0505050505050506 |
| loss (-) | 0.95049504950495 | 0.95049504950495 | 1.0505050505051 | 0.9504950495049505 |

All original and replacement CSV SHA256 identical within each source-sign control; wrong-sign control deliberately differs by >0.04. Artifact #14852425163 ZIP SHA256 `30df4d84a3bd3e8fdb1bf27d1f9f24ed2462105c926a32fefa1c4c7e52a7c267`. This is a *bounded normalized nonlinear source and implicit time-response test*, **NOT full S5-R coupled science or full AD Jacobian verification**. Exact-head S5-R P0 [#45239996694](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45239996694) also SUCCESS.

## Consumers and unfinished retirement gates
Live H05, R2, EI20, EDETACH, EI16, EI01, Issue402 and S5-R input/CI generator/contract paths still require controlled migration. EI18/EI19 negative assertions and S5-D heavy-only negatives require *semantic* no-electron-source controls; do not blanket-ban `FVCoupledForce` because it also projects energy. Frozen historic documents, C/H source attestations, dynamic/external consumers and old-input support policy are independent. Do not suppress or rewrite positive CI simply to make old Factory disappear.

This clean branch retains only source evidence/modules/tests/docs. Three branch-only temporary `issue817-*-once.yml` Workflows have been removed after their immutable run/artifact capture. No deletions of GitHub run history. **`SAFE_DELETE=HOLD / FULL_AD=NOT_VERIFIED / S5R_CURRENT_BINARY=THERMAL_DEPENDENCY_HOLD / MAIN_D9_POISSON_UNCHANGED`.**
