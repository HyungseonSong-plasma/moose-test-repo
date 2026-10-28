# Boltzmann CI EEPF artifact: native C++ development controls (S5)

**Scientific acceptance: HOLD_REAL_COLLISION_PROCESS_EQUIVALENCE.**

## Actual CI execution

Repository CI workflow has an independent parallel job named
"Native Boltzmann EEPF development controls" that compiles
PhysicsBoltzmannElasticSolver.C into a native executable and runs it
for six explicit, matched-metadata representative BOLSIG+ 07/2024
cases. Actual C++ output is preserved by actions/upload-artifact@v4
under the name boltzmann-native-eepf-synthetic-controls.

First verified execution: GitHub Actions run 40680402838, commit
d5ff81b0b9b2f634ed7550331d073706aaa59fe3.
Job conclusion: SUCCESS.
Artifact ID: 12812582216.

The EEPF values come from executing the repository's C++ solver, **not**
from invented plotted curves or Python emulation of the Boltzmann
equation. The new runner is
physics_app/ci/boltzmann_ci_eepf_controls.C,
with compiler/validation orchestrated by
physics_app/ci/export_boltzmann_ci_eepf.py.

All collision cross sections in these experiments are *invented*
elastic constants equal to 5.0e-20 m2, with approximate target mass
ratios. These are not the native source PHELPS/SIGLO collision
cross sections. The C++ CI model omits all of the native EXCITATION,
IONIZATION, ATTACHMENT and EFFECTIVE momentum scattering. It cannot
represent RF nonzero angular frequency for Example 2 cases R2–R10.
A diagnostic overlay is scientifically legitimate ONLY when
both curves are explicitly distinguished by physics model and
marked *not parity*. No meaningful relative-error PASS threshold
may be applied across these mismatched process inventories.

## Actual selected native CI output compared against user references

Case                       BOLSIG mean eV    C++ synthetic mean eV
example1_R21                  4.96374           7.669102863508882
example2_R1_DC                6.94903          27.433428675214910
example3_R31                  5.37619          10.549126648407675
example3_R33                  5.01202           9.014187981220920
example3_R35                  5.97496           7.365158210811475
example4_R1                   1.35694           8.636201906025788

The examples use exactly the printed E/N, gas fractions, temperature
and BOLSIG+ auto-selected maximum energy from the relevant native
runs, but intentionally use different collision process physics.
Example 2 only R1 uses DC; other Example 2 RF cases are not claimed.
The CI exporter checks finite nonnegative EEPFs, finite mean energy,
energy cell-center mapping, 1e-10 normalized EEPF mass tolerance,
positive valid gas fractions, and no missing run output.

For genuine BOLSIG+ parity, obtain a rights-controlled full native
cross-section file and implement correct EFFECTIVE cross-section
semantics, full nonlocal inelastic/growth channels and three-body
attachment, then match energy grid and solve EEPF with same growth
model, compare weighted normalization and transport moments.
Keep draft PR 408 on HOLD until the physical model equivalence gate.
