# Example 1 native EEPF vs M8 nonuniform C++ — independent rerun (2026-10-28)

This is the BOLSIG+ official Example **1** (not Example 4's four grid sizes).
The source is the user-supplied BOLSIG+ 07/2024 `example1-eepf(1).dat`
with 40 R1–R40 native EEPF blocks. Actual GitHub-CI-built C++ M8 was
rerun 40 times against six original PHELPS/LXCat 2013 Ar+He processes
locally; no original collision or native output table is committed.

## Physics and numerical conditions

- Ar = 0.1, He = 0.9; E/N = 0.1–100 Td (31 log runs), 200–1000 Td
  (9 linear runs), `omega/N=0` (DC).
- Tg=Texcitation=300 K, gas density=1e18 m^-3, ionization degree=0,
  temporal electron growth, equal-sharing ionization, 07/2024
  threshold/extrapolate=1.
- BOLSIG+ requests **400 automatic grid points**, solver precision
  1e-10 and convergence target 1e-4.
- Our C++ uses **256 power-law nonuniform cells**, `power=2`, and
  `--bolsig-2024-boundaries --solve-coupled-temporal-growth`.
- Our `Emax=max(35 eV, native actual output Emax)` includes all native
  printed energy support and keeps high-threshold ionization in the
  collision inventory. Because native Emax is used to set the upper
  support, the Emax choice here is **not** an independent predictive
  energy-domain calculation. Historic uniform results used a different
  upper-energy heuristic for high E/N; uniform-vs-nonuniform differences
  at high fields must not be attributed solely to mesh geometry.

## Cryptographic provenance

- PHELPS/LXCat original SHA256:
  `b8b1ff807d0586795dcabf4511a2a44b8b04828626b45e0fd95a319817c01063`.
- Private Ar+He 6-process selection SHA256:
  `ab14b68a3cdd8b7166c5b7243c4ce83d2d9015341028050ad792fbb4ce4dfa9d`.
- Native Example 1 output SHA256:
  `3802d6176ca57732310a00ea3b292cb7c91a1adafe118e1dad04c6e0183bec16`.
- CI-compiled C++ M8 binary SHA256:
  `c036ad1e46d29c3fd7610616ae1e6cc1ed82b6b5fdf61cec2e1d522b42ee05fd`.

## Real BOLSIG+ vs C++ observations

All **40/40 C++ runs computed** with nonuniform p=2; only **34/40**
native outputs report `Error code=0`. R35–R40 (500–1000 Td)
report native error `-1`, and their numeric discrepancies **must not**
be scored as validated BOLSIG+ physical parity.

Across the 34 BOLSIG+ `Error code=0` runs:

| Statistic | Historical 256 uniform C++ | New M8 256 p=2 C++ |
| --- | ---: | ---: |
| Median absolute relative mean-energy error | 0.0693200% | **0.0271011%** |
| Median sqrt(E)-weighted EEPF L1 on printed native interval | 0.0210299 | **0.0125464** |

Representative native vs new compiled C++ values:

| EN (Td) | Native mean energy (eV) | C++ mean energy (eV) | Abs. relative error |
| ---: | ---: | ---: | ---: |
| 0.1 | 0.0923585 | 0.0925516717 | 0.209154% |
| 1 | 0.616219 | 0.6164448000 | 0.036643% |
| 10 | 4.96374 | 4.9636736843 | 0.001336% |
| 100 | 9.53695 | 9.5451920334 | 0.086422% |
| 200 | 13.712 | 13.7991214162 | 0.635366% |
| 300 | 18.6986 | 19.0662588093 | 1.966237% |
| 400 | 24.4389 | 25.4152598442 | 3.995106% |
| 1000 | 69.559 | 83.1005278479 | 19.467686% (native error -1) |

For low field R1, changing only p at fixed 256 cells and Emax=35 eV:
p=1 -> 9.5738% error; p=1.5 -> 0.7171%; p=2 -> 0.2092%;
p=2.5 -> 0.1082%; p=3 -> 0.0750%.
At 400 Td, even p=3 at 256 cells / native-matched Emax gives
~3.9833% mean error, so low-energy mesh refinement by itself
**does not** resolve the high-field discrepancy.

The L1 calculation integrates sqrt(e)*|f_cpp(e)-f_native(e)| over
the printed native energy range; native points are linearly
interpolated, C++ finite-volume f0 is piecewise constant.
For graphics, **BOLSIG+ black dashed** and **our C++ orange solid**.

All 40 C++ curves, their edges, derived-only CSV and summary, and
a private-reproduction script are provided to the user as separate
conversation artifacts. The repository doc deliberately has no
original source cross-section or native printed EEPF rows.

## Science gates

This benchmark provides a strong low-/medium-field confirmation
of the nonuniform M8 improvement, not a completed arbitrary-field
or production physics validation. Determine the persistent
200–400 Td discrepancy, compare converged native 500–1000 Td data,
and establish an independent automatic/threshold-aware mesh policy
without native-Emax selection before a production acceptance claim.

**HOLD_EXAMPLE1_GENERAL_PHYSICS_PARITY**; PR #408 stays Draft;
`main` and production Oxygen ICP remain unchanged.
