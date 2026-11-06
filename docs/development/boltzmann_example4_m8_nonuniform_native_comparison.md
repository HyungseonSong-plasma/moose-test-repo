# BOLSIG+ 07/2024 Example 4 — actual M8 nonuniform C++ benchmark

**Date:** 2026-10-28. **Scope:** Standalone actual compiled C++ M8 compared against
user-owned genuine BOLSIG+ Example 4 EEPF, **not** four uniform mesh cases
and not production Oxygen ICP. PR #408 remains Draft and physics HOLD.

## Native conditions and private collision provenance

- Composition **Ar/He/N2/O2 = 0.70/0.20/0.08/0.02**,
  **E/N=10 Td**, **omega/N=0 (DC)**, Tg and excitation temperature 300 K.
- Neutral density 1e18 m^-3, ionization degree zero, temporal growth,
  equal secondary electron energy sharing; BOLSIG+ 07/2024 source extrapolation.
- Native requested **200 automatic** cells, actual adapted Emax **15.8367 eV**,
  **195 printed EEPF samples**, mean electron energy **1.35694 eV**.
- Selected real PHELPS/LXCat 2013 source has **47** collision processes.
  Exactly one source **O2 two-body dissociative attachment** record is
  absent from native 47-process output; source selection reproduces this
  numerical set but is **not a general O2 chemistry choice**.
  The included **O2 three-body attachment** source is tabulated with
  density-dependent units: native output was matched *as tabulated*,
  but independent physical density normalization is still unresolved.
- Original LXCat source SHA-256:
  `b8b1ff807d0586795dcabf4511a2a44b8b04828626b45e0fd95a319817c01063`.
- Native BOLSIG+ output SHA-256:
  `aa6c7c0ce00c61095934defa70f40e415474562b5e3e53374766c1ab7d6912d3`.
- Actual compiled M8 C++ binary SHA-256:
  `c036ad1e46d29c3fd7610616ae1e6cc1ed82b6b5fdf61cec2e1d522b42ee05fd`.
- A private 47-block source was reconstructed locally by preserving
  original physical process blocks in source order, SHA-256
  `05be1cfb1a1bc177e42f30c08694ff4373ba2293c99e65e0549ed03d3586f05f`.
  Original user-owned LXCat process rows are NOT committed/distributed.
  Its 200-cell uniform C++ output reproduces the previously validated
  200-cell mean and transport moments at machine-level precision.

## M8 measured native comparison

Both C++ runs use the **native-informed** fixed Emax of 15.8367 eV.
The native grid is *automatic*; C++ uses explicit finite-volume cells
and optional power-law edges `e_i=Emax*(i/cells)^p`.

| Property | Native BOLSIG+ | C++ uniform 200 p=1 | C++ nonuniform 256 p=2 |
| --- | ---: | ---: | ---: |
| Mean energy (eV) | 1.35694 | 1.3539538647 | 1.3524149278 |
| Mean energy relative error | ref | **0.220064%** | 0.333476% |
| sqrt(E)-weighted absolute EEPF L1, native printed interval | ref | 0.0155840855 | **0.0094339092** |
| Electron mobility × N relative error | ref | 0.167425% | **0.148083%** |
| Electron diffusion × N relative error | ref | **0.033568%** | 0.036117% |
| Energy mobility × N relative error | ref | **0.297767%** | 0.368239% |
| Energy diffusion × N relative error | ref | 0.035444% | **0.034317%** |
| Positive nonelastic process rate relative error median (41 rates) | ref | **0.990747%** | 1.613352% |
| Maximum positive rate relative error | ref | **7.94891%** | 13.01969% |

Actual 47-process C++ eigen residual for nonuniform p=2:
**1.13e-15**; EEPF mass normalization difference ~**1.11e-16**;
high-tail-to-peak ~**9.41e-12**. All 43 nonelastic/particle-change
channels were aligned by native process order (41 positive and
two He processes inactive above actual Emax).

**Important interpretation:** New p=2 reduces the native printed
energy interval EEPF-weighted absolute L1 by **39.46%**,
but does **not** improve all moments: mean energy and positive
reaction-rate errors increase. Largest rate difference is
**Ar ionization** with 15.8 eV threshold extremely close to the
15.8367 eV high-energy cutoff; do not generalize this relative error
to physical high-energy ionization without resolving Emax and tail.

Additional M8 numerical mesh sensitivity:
- 200 p=2: L1 0.005348; mean energy relative error 0.296681%.
- 256 p=1: L1 0.011993; mean error 0.281521%.
- 256 p=1.5/2/2.5/3: L1 0.009877/0.009434/0.009465/0.009671.
These errors are **native-reference differences**, not proof of
monotonic discretization convergence; 200 p=2 outperforming 256 p=2
on L1 specifically is a warning against treating a reference difference
as an asymptotic mesh-order study.

## Interpretation, graph convention and remaining gates

BOLSIG+ native EEPF shown **black dashed**, C++ M8 p=2 EEPF
**orange solid**. User received full linear/log EEPF plots,
low-energy focus, four transport-moment plots, per-channel
rate comparisons, 8-grid sensitivity metrics and source-free
C++ JSON outputs. No third-party original cross-section blocks or
native numeric EEPF rows were uploaded to GitHub or embedded in CI.

The score integrates `sqrt(energy)*abs(f_cpp-f_native)` on the
**195 native printed energy sample coordinates**, approximating C++
piecewise-constant FV EEPF. It is neither a relative percentage nor
an unbounded-energy-space L1 metric.

**Science status: HOLD_EXAMPLE4_PROCESS_AND_DENSITY_EQUIVALENCE.**
Need independent O2 three-body attachment physical density scaling,
the native omitted two-body attachment selection rationale,
predictive Emax and threshold-aware grid convergence, and broader
chemistry-coupled validation before production acceptance.
Do not merge PR #408 or change main / Oxygen ICP production code.
