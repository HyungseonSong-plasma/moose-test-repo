# BOLSIG+ Example 3: actual original EEPF versus M8 C++ (2026-10-28)

## Native source located and previous conditions corrected

The user's Library includes the original **example3-eepf.dat**, a
761314-byte BOLSIG+ 07/2024 output containing **100 individual
R1–R100 EEPF blocks**, plus the 52320-byte **example3.dat** RUN2D
transport table. The prior documentation wrongly reported that
Example3 native EEPFs were absent. The original output was read
locally through authorized Library text windows; no raw LXCat data
nor native EEPF rows were committed to the public repository.

**Crucial correction:** The native BOLSIG+ EEPF RUN headers explicitly
contain Ar/He fractions **1/0, 0.75/0.25, 0.50/0.50, 0.25/0.75, 0/1**.
The earlier C++ predicted 100 runs with He=0,0.2,1/3,3/7,0.5,
mistakenly normalizing the condition 1. VAR. Those old 100 C++
predictions and the “He up to 50%” claim are **SUPERSEDED**. All 20
quadratic E/N values were recovered directly from original RUN headers.

## Physics and discretization

- 20 quadratic E/N points (0.1–100 Td) × 5 mixtures = **100 RUN**.
- 300 K gas and excitation, zero AC frequency, 1e18 m^-3 neutral
  density, temporal growth, equal-share ionization, zero ionization
  degree, PHELPS/LXCat June 2013 elastic effective/inelastic processes.
- BOLSIG+ native: 100 **automatic** energy-grid points,
  precision 1e-10, convergence 1e-4, cross-section extrapolation on.
- GitHub-built real C++ M8: 256-cell power-law **nonuniform p=2**,
  conservative FV with EFFECTIVE full scattering, ionization/excitation
  and temporal-growth eigenproblem.
- C++ Emax = max(35 eV, 1.1 × original BOLSIG+ actual Emax).
  This is **native-informed** and does NOT prove independent Emax
  selection or automatic grid equivalence.

## Direct 100 RUN native vs C++ scientific results

All **100/100** C++ runs were executed with the corrected original
mole fractions and exact native field values.

| Diagnostic | Median | Max | Max RUN |
| --- | ---: | ---: | --- |
| Mean energy absolute relative difference | **0.008748%** | **0.243796%** | R5 (pure He, 0.1 Td) |
| sqrt(E)-weighted EEPF L1 over native samples | **0.00021995** | **0.00544998** | R5 |
| Reduced mobility difference | 0.023235% | 0.648322% | R100 |
| Reduced diffusion difference | 0.038698% | 1.130458% | R96 |
| Reduced energy mobility difference | 0.023453% | 0.680106% | R100 |
| Reduced energy diffusion difference | 0.030514% | 0.871695% | R100 |

The EEPF score is trapezoidal quadrature of
`sqrt(E)*abs(f_cpp(E)-f_native(E))` on native printed sample points,
not a percentage or full-domain L1. The native 100-point **requested**
automatic grid can produce fewer than 100 **printed** points.

Per-target nonzero rates, with target present and native value at
least 1e-6 times the channel maximum:

| Rate | Comparison count | Median difference | Maximum |
| --- | ---: | ---: | ---: |
| Ar excitation 11.5 eV | 64 | 0.05603% | 0.43600% |
| Ar ionization 15.8 eV | 51 | 0.17912% | 1.37634% |
| He excitation 19.8 eV | 15 | 0.11820% | 0.47550% |
| He ionization 24.58 eV | 15 | 0.33364% | 1.56370% |

The user-local evidence archive has all 100 genuine EEPF comparisons
(**native black dashed / C++ orange solid**), a 20-case representative
figure, 100-run CSV, energy/transport metrics, rate comparisons,
heatmap and C++ output arrays. Private third-party raw collision rows
and original native EEPF samples are not redistributed.

**Scientific status: HOLD_GENERAL_MODEL_PARITY.** This is a strong
specific native Example 3 comparison, not independent automatic
Emax qualification, electron-electron physics or production acceptance.
Keep PR #408 Draft; main and production Oxygen ICP untouched.
