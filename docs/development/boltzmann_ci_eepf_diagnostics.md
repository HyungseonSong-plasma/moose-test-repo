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

## S7: EFFECTIVE reconstruction and independent native N2-cooling discriminator (2026-10-28)

The C++ BOLSIG-format steady elastic+excitation projector now accepts an
EFFECTIVE (or MOMENTUM) record *only for its supported excitation-only process
inventory*. It reconstructs the elastic energy-loss contribution as
sigma_elastic = sigma_effective - sum(sigma_excitation), using a union of
source energy knots and threshold positions. The existing two-term transport
operator adds excitation momentum only once. It rejects a negative elastic
remainder and duplicate ELASTIC/EFFECTIVE momentum suppliers for a target.
Ionization, attachment and rotation in the same steady input remain
unsupported: a complete real BOLSIG+ process inventory must NOT be projected
into this subset by dropping those channels. Temporal-growth and full
first-harmonic momentum correction are not solved by this change.

Independent synthetically constructed equivalent ELASTIC versus EFFECTIVE
inputs, rates and conservation regressions are encoded in
`tests/boltzmann/cross_section_import_test.C`; these are P0/P1 tests, not
an experimental LXCat/BOLSIG+ cross-section match.

[Repository CI run 40683761894](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40683761894)
at development head `da04277170db968204b6d708fcbb2b5936c5cf99`
completed its dedicated **Native Boltzmann EEPF development controls** job
successfully. Its [artifact 12813253936](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40683761894/artifacts/12813253936)
contains eleven real, compiled-C++ EEPFs, including two entirely
first-party *invented* N2 vibrational excitation controls. Exact same
synthetic constant elastic collision physics, E/N = 10 Td and mixture
Ar/He/N2/O2 = 0.70/0.20/0.08/0.02:

| Emax (eV), cells | Elastic only mean (eV) | Elastic + two synthetic N2 excitations mean (eV) |
| --- | ---: | ---: |
| 15.8367, 200 | 8.6362019 | 0.5383772 |
| 31.6734, 400 | 12.978518 | 0.5383772 |

The added excitation channels use **invented**, not BOLSIG+/PHELPS/SIGLO,
cross sections: 0.3 eV threshold and 5e-20 m2 above threshold; 1.0 eV
threshold and 4e-20 m2 above threshold. They are a mechanism discriminator
demonstrating conservative low-energy cooling and cutoff stability for
this synthetic subset, **not** a fitted or physically accepted N2 operator.
Their 0.5384 eV mean *undershoots* the actual BOLSIG+ Example4 mean
1.35694 eV; therefore this is emphatically **not** improved quantitative
BOLSIG+ parity. Both models' absolute EEPFs remain non-equivalent to the
47-process real source, and no physical-rate/transport PASS is allowed.
The dedicated job PASS does not promote overall Repository CI or P2/P3.

For genuine BOLSIG+ parity, retain source-provenance-controlled **complete**
47-process data including effective momentum semantics, excitation,
ionization, attachment, electron temporal growth and inverse populations
where applicable, plus independent raw reference EEPF export. Then require
cutoff/cell-size convergence and independent EEPF, rates and four transport
moments comparisons. The imported third-party source must not be redistributed
without authorization. Keep PR #408 in DRAFT / SCIENCE HOLD.
