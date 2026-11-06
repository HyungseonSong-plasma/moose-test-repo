# BOLSIG+ Example 4 — genuine 47-channel independent Python FV diagnostic (2026-10-28)

## Evidence custody and interpretation

This is a user-local numeric diagnostic using the user's actual LXCat source and
original BOLSIG+ 07/2024 output. The original and selected third-party table
bytes are **not committed**. It is **not** a run of the repository C++ candidate
binary and **does not** establish physical equivalence or production acceptance.

- Original source SHA-256:
  `b8b1ff807d0586795dcabf4511a2a44b8b04828626b45e0fd95a319817c01063`.
- User-local explicitly selected 47-channel source SHA-256:
  `daf82ef4927fabec32bed5b5b19214b432f580931518d21e1aa6d3a438751bac`.
- Native BOLSIG+ 07/2024 EEPF SHA-256:
  `aa6c7c0ce00c61095934defa70f40e415474562b5e3e53374766c1ab7d6912d3`.
- Mixture: Ar 70%, He 20%, N2 8%, O2 2%; E/N 10 Td; Tg 300 K;
  native actual Emax 15.8367 eV; native mean energy **1.35694 eV**.
- All 47 selected process identities retained; the absent original O2
  two-body attachment is tracked through user-approved source selection, not
  silently discarded. The retained O2 three-body-labelled attachment is used
  *as tabulated* in this native-output replication, and its physical density
  conversion remains an unresolved science gate.
- He high-threshold excitation 19.8 eV and ionization 24.58 eV are
  retained as zero-rate inactive processes at Emax=15.8367 eV.

## Independent method — explicitly not C++

A standalone author-created Python/NumPy/SciPy 200-cell finite-volume
reconstruction was run against the private 47-channel input:

1. Apply documented BOLSIG+ 07/2024 opt-in source knot semantics
   (threshold zero insertion, low-energy holding, 1.5x high-energy
   `ln(E)/E` continuation and linear segments); no normalization or
   fitting of raw cross-section values.
2. Use the source EFFECTIVE total first-harmonic scattering for field heating;
   reconstruct nonnegative elastic recoil by subtracting all included
   excitation, ionization and attachment cross sections at each face.
3. Assemble Scharfetter–Gummel elastic drift/diffusion; conservative
   excitation downshifts; two-electron equal-share ionization gain;
   attachment sink; all rates divided by neutral number density.
4. Solve the resulting 200x200 generalized dominant-growth eigenproblem
   using SciPy dense eigensolver, normalize the EEPF by the cell
   number-mass weights `(2/3)*(E_hi^1.5-E_lo^1.5)`, calculate
   mean energy from the `(2/5)*(E_hi^2.5-E_lo^2.5)` moment.
5. Evaluate a *sampled-interval* `sqrt(E)`-weighted absolute EEPF L1
   difference against native BOLSIG+ printed values. This is not a common
   adaptive-grid projection or proof of convergence.

No original cross-section table rows or native EEPF rows were committed.

## First real-source numerical results

| Comparison | Result |
| --- | ---: |
| BOLSIG+ mean energy | 1.35694 eV |
| Independent Python 200-cell mean energy | **1.3539538646317417 eV** |
| Mean energy relative error | **0.220064%** |
| Printed-interval energy-number-weighted EEPF L1 | **0.0155841** |
| Python generalized eigen residual | **2.15e-14** |
| BOLSIG+ weighted ionization coefficient | 4.33539e-24 m³/s |
| Python reduced growth (attachment included) | 4.2924536764e-24 m³/s |
| Approximate relative difference | 0.9904% |
| Minimum recovered elastic recoil across interior faces | 9.398788e-22 m² |

The ionization reference is not *exactly* the growth diagnostic because
attachment appears separately, although its recorded coefficient is tiny in
this particular native case. The quoted difference is a diagnostic only.

Across 41 positive *inelastic/particle-changing* process rates,
the median relative error was **0.9907%**. The largest difference
was **7.94%** for an extremely small Ar-ionization coefficient
(3.11552e-29 m³/s) at a threshold very close to the 15.8367 eV ceiling.
Do not score effectively zero/out-of-range rates as valid positives.

### Grid/domain sensitivity of the independent Python calculation

| Emax (eV) | cells | Mean energy (eV) | Relative mean error | EEPF weighted L1 |
| ---: | ---: | ---: | ---: | ---: |
| 15.8367 | 100 | 1.3602338194 | 0.2427% | 0.030833 |
| 15.8367 | 150 | 1.3556856820 | 0.0924% | 0.021091 |
| 15.8367 | 200 | 1.3539538646 | 0.2201% | 0.015584 |
| 15.8367 | 256 | 1.3531199283 | 0.2815% | 0.011993 |
| 31.6734 | 400 | 1.3539538647 | 0.2201% | 0.015584 |

The L1 difference improves with uniform resolution. Mean-energy error
against the *separately adaptive* BOLSIG reference is not monotonic,
and matching scalar values alone is insufficient. Doubling Emax at fixed
cell width barely changes mean energy, suggesting weak truncation
sensitivity for this configuration, not proving all high-tail processes
converged.

## Mandatory remaining acceptance gates

- Execute **the repository C++ candidate binary** against the private
  original-identity-selected 47-channel file with
  `--bolsig-2024-boundaries --solve-coupled-temporal-growth`, compare its
  output directly with native BOLSIG+ and with this *independent Python*
  oracle; a Python reconstruction cannot substitute for that test.
- Audit source process selection, low-energy threshold treatment,
  three-body attachment source-density units and the native BOLSIG+
  temporal-growth eigenvalue exactly.
- Benchmark transport mobility, diffusion, energy mobility and diffusion,
  rates, high-energy tail and automatic-vs-uniform grid error.
- Keep science state `HOLD_REAL_COLLISION_PROCESS_EQUIVALENCE`, PR Draft,
  main and production Oxygen ICP entirely unchanged.

The comparison is promising: real data are now numerically compatible
with an independent implementation of the intended model. This
statement is **not** a C++ test pass or an approval to merge.
