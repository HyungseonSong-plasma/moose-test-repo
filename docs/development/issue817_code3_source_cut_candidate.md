# Code3 #817 — isolated C/H retirement candidate

The **old** `PhysicsFVElectronReactionSource.C/.h` and its one Factory registration are removed here, not in D9/main. Source Git Blobs are retained in the immutable parent history: C `35ded0eab65ad7bed85baa0104261c90bc26bf3d`, H `5250b3500d6694481158e2abb896c7e1c6f349e9`. Source counts updated from 12 C/17 registered types to 11 C/16 types; D5 historical A/B remains pinned.

All current EI01/H05/R2/EI16/EI20/EDETACH signed electron-source producers have been migrated to `FVCoupledForce(v=original signed functor, coef=1)`; S5-R produces `FVCoupledForce(v=S_e_s5r,coef=1/n_ref)`. Frozen historic ownership/chemistry JSON not overwritten. The independent pre-cut native studies [EI01](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45230510538), [H05/R2](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45234619718) and [normalized nonlinear 1-cell](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45239977824) found bounded parity with negative controls. These are **not post-cut exact-head evidence**.

Historical S5-R remains blocked for **both** original and replacement by missing `PhysicsThermalDiffusionMaterial` in the current New-only binary ([diagnostic run](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45238738588)). Independent full coupled AD Jacobian and dynamic/external users are not proven; the old Issue224 setup experiment now compares heavy-only alternatives, retaining archived old evidence. Source cut is **staged, not SAFE_MERGE** until exact-head P0/P1/P2/P05 and needed P3 science pass.

**`C_H_CUT_IN_ISOLATED_CANDIDATE / MAIN_UNCHANGED / D9_UNCHANGED / SCIENCE_HOLD`.**
