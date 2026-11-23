# Code3 D1/D2 — source-locked consumer inventory and electron-only replacement preparation

- **Issue:** #817; parent #774; PR-A provenance #707. **New-only base:** `87b7d97113ce6e75081dd15c56c86bc159bde6c9` (Thermal D9), independent of #809 Code1 staged integration and Poisson #652.
- **Old Factory:** `PhysicsFVElectronReactionSource`; single source blob `35ded0eab65ad7bed85baa0104261c90bc26bf3d`; header blob `5250b3500d6694481158e2abb896c7e1c6f349e9`; **C/H and registration retained** in this phase.
- **Reused P0 input candidate:** [#707](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/707) original runner blob `0975c89f3072b782894566d43c5d2057afd9132f`, test blob `5d4433f3e08a714129efd824dcae9521626c68d1`. No old #707 CI/FDEG workflow imported.
- **Residual mapping candidate:** old signed electron source gives `-S_e` in physical and `-S_e/n_ref` in normalized state; standard `FVCoupledForce` candidate `v=S_e`, `coef=1` or `1/n_ref`. This is not independent AD/residual equivalence and must not be conflated with the heavy-species `PhysicsFVSpeciesReactionSource` or electron energy projectors.

## Actual D9 consumer blockers
- `physics_app/ci/check_stage5_h05_runtime.py`: H05 generated Native input **and** source-text invariant.
- `physics_app/ci/check_r2_o2_ionization_implementation.py`: R2 generated Native input **and** source-text invariant.
- `physics_app/ci/check_issue402_json_rate_native_p2.py`: H05 scratch stage asserts old type.
- `physics_app/ci/ei01_attachment_runtime_smoke.i`: direct active input, requires controlled old/new P2 + source-sign comparator.
- `experiments/historical_recipe_support/issue192_s5r.py`: generated source is imported from `experiments/Issue192_s5r_representative/run.py`; historical pathname **not** caller-zero proof.
- Further Stage5/EI20/EDETACH checker/JSON/Functor and any dynamic external consumers remain individually unclosed.

The `ci/guards/issue817_code3_retirement.py` census reads the exact tracked HEAD Git tree and line-level references and **fails closed if required active consumers or the frozen candidate/old source Blob IDs are missing**. It cannot observe execution or external data, and explicitly keeps `SAFE_DELETE=HOLD`.

## Gates
1. **D1 P0:** exact-head reference evidence, source/runner/tests SHA, guard negative tests; preserve all active CI. No literal text rewrite, broad CI suppression or historical auto-archive.
2. **D2 P0:** original PR #707 one-block A/B input replacement, including normalized nonunit and physical controls; reject missing, zero, negative, nan/inf `n_ref`, wrong type/source/state, non-target modifications. Tests prove *input construction*, not residual.
3. **D3 Native:** exact source W1 `physics-opt`, paired **old/new** P2 on real H05/R2/S5R, followed by P3 residual and AD Jacobian/charge/electron inventory oracle for both state forms and sign directions. No same-HEAD evidence = no qualified result.
4. **D4 deletion:** only after active CI/generator input migration with independent proof, C/H removed in separate branch commit. Re-run all gates and negative controls.
5. **D5-D6:** workflow cleanup, integration SHA lease, PR/issue/branch closure only when safe. Do not merge D9/main/Poisson now.

**Decision:** `D1_D2_PREPARED`, `C_H_DELETE=HOLD_ACTIVE_CONSUMERS`, `P3=NOT_EXECUTED`, `SCIENCE_HOLD`, `MAIN_MERGE=DEFERRED`.
