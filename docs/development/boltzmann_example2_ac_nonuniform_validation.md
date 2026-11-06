# BOLSIG+ 07/2024 Example 2 — real 10-run AC/nonuniform C++ validation (2026-10-28)

## Physical source and provenance

Original user-uploaded `example2-eepf(1).dat` contains all **10** EEPF
runs and their independently reported mean energies, in-phase
`Re/perp mobility*N` and quadrature `Im/Hall mobility*N` values.
The original PHELPS/LXCat Ar+He six-channel collision table remains
PRIVATE, not committed or embedded in any CI fixture.

- Native Example 2 output SHA-256:
  `8c2b2cc6710fd3fbd8b7beac4fa73b40345b3b861ff254b86ba638398210a440`.
- Original PHELPS/LXCat 2013 source SHA-256:
  `b8b1ff807d0586795dcabf4511a2a44b8b04828626b45e0fd95a319817c01063`.
- User-local explicitly selected six-process Ar+He source SHA-256:
  `ab14b68a3cdd8b7166c5b7243c4ce83d2d9015341028050ad792fbb4ce4dfa9d`.
- GitHub-CI-built actual C++ M8 binary with AC Re/Im transport SHA-256:
  `c036ad1e46d29c3fd7610616ae1e6cc1ed82b6b5fdf61cec2e1d522b42ee05fd`.

Native input: Ar 99%, He 1%, gas temperature 300 K,
excitation temperature 300 K, neutral density 1e18 m^-3,
ionization degree 0, electron-electron Coulomb model 3 (no electron
density), zero E-B cosine, temporal growth, equal secondary-electron
energy sharing, 200 automatic native grid points, 1e-10 precision,
1e-4 convergence, cross-section extrapolation 1.
In **BOLSIG+ 07/2024** the AC reduced field is **RMS** and
q = omega/N in rad.m3/s; its q=0 limit equals the DC equation.
The M8 developer C++ path uses the source total first-harmonic
cross-section, not double-counted excitation.

Source: Hagelaar, *Brief documentation of BOLSIG+ 07/2024*,
https://www.bolsig.laplace.univ-tlse.fr/wp-content/uploads/2024/07/bolsigdoc0724.pdf
(page 12 input AC RMS semantics; page 16 Re/Im mobility formulas).

## M8 discrete physics implementation

1. Build an optional power-law energy mesh
   `energy_edges[i] = Emax * (i / cells)^p`, `1 <= p <= 4`,
   and enforce strictly increasing endpoints. p=1 is original uniform,
   p>1 refines the low-energy electron thermal peak. This is **not**
   a claim to reproduce BOLSIG+'s automatic adaptive grid.
2. Use cell-centered finite-volume Scharfetter–Gummel with true adjacent
   center separations and geometric cell-integrated mass/moments.
3. Excitation, superelastic and equal-share ionization gains integrate
   overlap against **all** destination cells intersected by the shifted
   interval. On arbitrary widths, the old uniform two-cell shortcut
   is invalid; absolute conservation is verified in C++ regression.
4. Apply harmonic two-term RF energy-diffusion suppression:
   `Dfield = gamma * (EN²/3) * e / sigma_m *
      (1 / (1+(q/(gamma*sqrt(e)*sigma_m))²))`;
   at q=0 this reduces exactly to the original DC heating.
   **Do not multiply by an additional 1/2**: EN is AC RMS.
5. Compute source-independent real/imag AC mobility via
   `Q=total_momentum_cross_section(e), q_e=q/(gamma*sqrt(e))`;
   `Re mobility*N ∝ ∫ e (-df0/de) Q/(Q²+q_e²) de`,
   `Im mobility*N ∝ ∫ e (-df0/de) q_e/(Q²+q_e²) de`.
   DC mobility on the AC-heated EEPF is retained separately.

The default CLI remains DC+uniform when no new flags are supplied.
New flags: `--omega-over-N=<rad_m3_s>`,
`--energy-grid-power=<p>`, and the existing opt-in
`--bolsig-2024-boundaries --solve-coupled-temporal-growth
--report-coupled-growth-transport`. The JSON includes actual edges,
AC input, energy grid power, growth eigen residual and AC Re/Im mobility
on nonzero frequency. The repository's production O2 ICP transport
was NOT replaced.

## Actual source 10-run BOLSIG+ vs compiled C++ comparison

C++ used **256** cells, exponent **p=2**, and a fixed high-energy
support Emax >=46 eV (or 1.15x native actual Emax, whichever larger).
The energy ceiling and mesh differ deliberately from the native
automatically adapted 200-point grid, so this table demonstrates numerical
agreement but not identical discretization.

| RUN | EN (Td) | omega/N (m3/s) | Native mean eV | C++ mean eV | Absolute relative error |
| --- | ---: | ---: | ---: | ---: | ---: |
| R1 | 100 | 0 | 6.94903 | 6.949319623 | 0.004168% |
| R2 | 100 | 1e-16 | 6.94903 | 6.949318155 | 0.004147% |
| R3 | 100 | 1e-15 | 6.94889 | 6.949172844 | 0.004070% |
| R4 | 100 | 1e-14 | 6.93463 | 6.934704567 | 0.001075% |
| R5 | 100 | 1e-13 | 5.91854 | 5.911422203 | 0.120263% |
| R6 | 100 | 1e-12 | 2.52173 | 2.521513467 | 0.008587% |
| R7 | 100 | 1e-11 | 0.334038 | 0.333663947 | 0.111979% |
| R8 | 100 | 1e-10 | 0.0431771 | 0.043356390 | 0.415244% |
| R9 | 1000 | 1e-10 | 0.334036 | 0.333664274 | 0.111283% |
| R10 | 10000 | 1e-10 | 2.50858 | 2.508343011 | 0.009447% |

- All 10 actual C++ cases **completed**, no DC-for-AC substitution.
- Median relative mean-energy difference: **0.009017%**; max: **0.415244%**.
- Printed-native-interval `sqrt(E)`-weighted EEPF L1 median: **0.01112**;
  maximum **0.08728** (R8). This is a *distribution-shape*
  difference, not a percentage and not an automatic-grid parity proof.
- Independent C++ mass normalization within ~1e-15 and max generalized
  eigenpair residual < 5e-12 for the ten cases.
- AC real mobility relative errors (9 AC runs): median **0.04237%**,
  maximum **0.37162%**.
- AC imaginary mobility relative errors (9 AC runs): median **0.06596%**,
  maximum **0.84824%**. Small imaginary mobility at low frequency
  is particularly sensitive to interpolation; do not conflate
  `Re mobility` with DC transport mobility.

### Why nonuniform matters: native R8 low-energy stress test

At 100 Td, q=1e-10 m3/s, Emax fixed at 46 eV, native mean 0.0431771 eV:

| Grid | cells | C++ mean eV | Relative mean-energy error |
| --- | ---: | ---: | ---: |
| Uniform p=1 | 200 | 0.1380731 | **219.78%** |
| Nonuniform p=1.5 | 200 | 0.0447948 | 3.7466% |
| Nonuniform p=2 | 200 | 0.0434761 | 0.6925% |
| Nonuniform p=2 | 256 | 0.0433564 | 0.4152% |
| Nonuniform p=2.5 | 256 | 0.0432466 | **0.1610%** |

A tiny normalized eigenvalue residual by itself **does not**
fix a grid that poorly resolves the electron-energy peak.
Power-law refinement yields a drastic improvement in actual
reference agreement without altering cross-section values.

## Reproducibility / acceptance

For the 10-run private reference and collision data, execute
the user-local `compare_example2_ac.py` bundled in the private
analysis archive using the verified GitHub C++ binary.
The output includes graph overlays, mean-energy frequency sweep,
per-run metrics, low-energy grid study, solver SHA256 and
provenance. Third-party raw collision rows and native EEPF rows
are NOT redistributed in the public repository.

The source contract is real-data input, not a synthetic-only benchmark.
CI tests use **author-owned synthetic** cross sections, checking
DC zero-frequency invariance, nonuniform mass normalization,
energy-shift overlap conservation, strong AC cooling, and nonzero
AC Re/Im mobility. Existing steady DC paths remain unchanged.

**Science status: HOLD_GENERAL_MODEL_PARITY.** The real Example 2
specific benchmark is strong. Before *production* use, qualify
the automatic grid, rate and energy-loss moments over all conditions,
electron-electron collisions where physically present, arbitrary
gas mixtures, and closure/ionization response. Example 4 O2
three-body attachment unit semantics remain independently HOLD.
Keep PR #408 Draft and main/production O2 ICP unchanged.
