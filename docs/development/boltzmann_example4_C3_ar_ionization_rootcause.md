# Example 4 C3 Ar ionization: near-threshold rate-error root cause (2026-10-28)

## Scope and immutable inputs

Compared genuinely executed, user-local **BOLSIG+ 07/2024 Example 4**
(Ar/He/N2/O2 = 0.7/0.2/0.08/0.02, E/N=10 Td, Tg=300 K,
temporal growth, 47 selected real LXCat processes) with actual GitHub
CI-built **M8 C++** eigen-solves:
- BOLSIG+ rate **C3 Ar ionization = 3.11552e-29 m3/s**.
- M8 200-cell uniform p=1 = **3.363169882461393e-29**
  (**+7.948910%** signed bias).
- M8 256-cell nonuniform p=2 = **3.521151040665634e-29**
  (**+13.019690%** signed bias).
- Original source Ar ionization threshold = **15.8000 eV**;
  actual native Emax = **15.8367 eV**.
- Only **0.0367 eV** of the domain contains ionizing electrons;
  the exact native printed EEPF **ends at 14.97833 eV** despite
  195 printed samples. Thus *no native EEPF sample exists in the
  active C3 interval*; visual/global EEPF parity says nothing
  directly about the C3 source integral.

## Independent source-integral verification

In [15.8,15.8367] eV the actual Ar C3 source cross-section is the
linear onset segment, sigma(E) = S*(E-15.8), S = 1.01e-21 m2/eV.
The C++ source PhysicsBoltzmannGrowth.C uses piecewise-linear
sigma and **exact polynomial integration** of E*sigma(E) per FV cell.
The independent Python evaluation of the source integral agrees
with the compiled C++ rate to better than 1e-10 *relative* across
**eight independently computed mesh variants**. No evidence suggests
that a wrong threshold or cross-section quadrature explains the
existing C3 discrepancy.

For the C++ p=2, 256-cell result, the **last cell only**
contains the ionization window:
- cell edges: **15.71321743–15.8367 eV** (width **0.12348257 eV**);
- cell center: **15.77495872 eV**, *below* C3 threshold;
- EEPF cell value: **5.51577281e-12 eV^-3/2**;
- active window occupies just 29.72% of the cell width;
- C++ uses that same constant f0 for the entire active 0.0367 eV.
Because high-energy EEPF is falling quickly, this extrapolates
a too-high cell-center f0 into the ionizing part of the cell.

From the exact sigma integral and the **native rate only**, the
reference-weighted tail average f0 would be **4.88036449e-12**,
vs the C++ piecewise constant **5.51577281e-12**. This
13.02% difference exactly matches the rate bias.
This is a **back-calculated integral average**, not a measured
native pointwise EEPF above 15.8 eV.

## Numerical diagnostic: reconstruction of the SAME frozen C++ EEPF

To isolate the shape omission, reconstruct log(f0(E)) from the
last 2, 3 or 5 C++ cell-center values and integrate
E*sigma(E)*reconstructed_f0(E) over [15.8,15.8367].
This is **postprocessing only**; neither the conservative FV
collision source nor the temporal-growth eigenvector is recomputed.

| Grid | Baseline cell-constant C3 bias | Two-point log-tail bias | Three-point log-tail bias |
| --- | ---: | ---: | ---: |
| 200-cell uniform p=1 | +7.949% | +4.028% | +2.745% |
| 256-cell uniform p=1 | +5.477% | +3.276% | +2.534% |
| 256-cell nonuniform p=2 | **+13.020%** | **+3.060%** | **+0.375%** |
| 256-cell nonuniform p=2.5 | +18.874% | +3.337% | -0.156% |
| 256-cell nonuniform p=3 | +26.286% | +4.117% | +0.035% |

The p=2, 256-cell corrected diagnostic gives:
- 2-point: **3.21084345e-29 m3/s** (+3.060%);
- 3-point: **3.12721727e-29 m3/s** (+0.375%);
- 5-point: **3.03784754e-29 m3/s** (-2.493%).

**Interpretation:** A large majority of the +13% baseline
C3 discrepancy is associated with representing a strongly varying
tail by one constant cell value. However, the difference between
2/3/5-point reconstructions is **model/reconstruction uncertainty**;
do NOT select the reconstruction that best matches BOLSIG+ and
claim independent physics parity. A self-consistent re-solve with
threshold-aligned/high-energy refined cells is required.

## Cutoff sensitivity (held EEPF frozen; geometric test only)

Because sigma(E) starts linearly, the near-threshold rate scales
approximately with **(Emax-threshold)^2**.
Holding f0 fixed, moving Emax by only **±0.001 eV** changes
the C3 rate by **-5.379%/+5.528%**. This is not an actual
observed native-vs-C++ Emax mismatch — both runs used the
native Emax — but illustrates why an independent Emax/convergence
policy is mandatory before production use.

## Practical impact and required fix

The actual BOLSIG+ total mixture-weighted ionization/N is
**4.33539e-24 m3/s**, while the contribution of C3 is
Ar_fraction(0.7)*C3 = **2.180864e-29 m3/s**, only
**0.0005030%** of total ionization. The p=2 C3
overprediction alone contributes merely **0.0000655%**
of that total reference. C3's relative rate error is serious
for a C3 process-parity benchmark, but not evidence of a 13%
error in the total ionization/growth.

**Development recommendation:** preserve p>1 low-energy refinement
but place energy-cell faces near *active* inelastic thresholds,
particularly within a few meV of Emax. Implement a
positivity-preserving within-cell reconstruction (or
subcell reaction quadrature consistently coupled to the FV
particle-changing operator), and repeat independent N/p/Emax
convergence. Separate errors from EEPF/transport solve,
energy ceiling, and per-process rate integration. Verify
source/gain conservation and equal secondary energy sharing.

**Root cause verdict:** highly supported numerical
**last-cell constant-EEPF reconstruction/near-cutoff sensitivity**,
not a proven wrong Ar ionization cross section or collision
integral implementation. Residual high-energy EEPF
and native automatic-grid equivalence remain unverified because
the native EEPF samples stop below the C3 threshold.

**HOLD_EXAMPLE4_C3_HIGH_THRESHOLD_RATE_PARITY**;
PR #408 remains Draft, main and production Oxygen ICP unchanged.
