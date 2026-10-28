# BOLSIG+ official Examples 1–4: 151-run scope and honest reference coverage

**2026-10-28 correction:** The four official examples are distinct physical
sweeps, NOT four resolutions of BOLSIG+ Example 4. Source of truth:
user-provided 240-line input-examples-with-example4-eepf.dat.

| Official example | Conditions | Native requested automatic grid | Number of runs | Native reference |
| --- | --- | ---: | ---: | --- |
| 1 | Ar=0.1 He=0.9; E/N=0.1–100 Td, 31 exponential points; 200–1000 Td, 9 linear points | 400 | 40 | example1.dat MISSING |
| 2 | Ar=0.99 He=0.01; 8 RUN values at 100 Td and omega/N=0…1e-10; 1000 and 10000 Td at omega/N=1e-10 | 200 | 10 | example2.dat MISSING |
| 3 | Ar:He input 1:VAR (0–1), normalized to unity, 20 quadratic E/N points × 5 linear VAR values | 100 | 100 | example3.dat MISSING |
| 4 | Ar/He/N2/O2=0.70/0.20/0.08/0.02; E/N=10 Td; 300 K | 200 | 1 | example4-eepf.dat AVAILABLE |

Crucial Example 3 detail: Ar = 1/(1+VAR), He = VAR/(1+VAR); at
VAR=1, He fraction is **0.5**, not 1. The internal Type=2 quadratic
E/N abscissa has been provisionally modeled as a square-spaced axis;
verify the actual intermediate E/N points against original native
example3.dat before claiming an exact reproduction.

## Actual original-collision C++ execution coverage

The user-local analysis ran a genuine GitHub-compiled C++ candidate against
the user's actual Ar/He collision blocks and the verified Example 4
47-process selected collision table, without uploading third-party tables.

| Example | C++ cases executed | Scientific constraints |
| --- | ---: | --- |
| 1 | 40/40 | Original requests 400 automatic energy points, but C++ dense limit is 256 uniform cells; **11** cases flagged low-energy resolution |
| 2 | 1/10 | Only exactly zero frequency DC; **9** nonzero-frequency cases unsupported by current C++ AC operator |
| 3 | 100/100 | **14** low-energy-resolution warnings and provisional quadratic E/N spacing |
| 4 | 1/1 | Actual native-reference EEPF/transport parity quantified separately |
| **Total** | **142/151** | Native agreement available only for the Example 4 reference |

Low-energy resolution warning is explicitly flagged if candidate mean
energy / uniform energy-cell width < 5; this is a diagnostic threshold
rather than a convergence proof. Example 1 C++ used 256 uniform cells
in place of the BOLSIG+ 400-point **automatic** request. For 1–3,
C++ Emax was a documented user-local heuristic, extended only when
high-tail guards rejected a run; never misrepresent it as the unknown
native automatic Emax. All 9 AC cases remain unsupported; they were
not substituted by DC calculations.

Native-independent EEPF and transport agreement **cannot** be measured
for Examples 1–3 until original example1.dat, example2.dat and example3.dat
are supplied. A BOLSIG+ input script is not a numerical reference.
For Example 4, the actual reference gave mean energy 1.35694 eV;
real C++ 200-cell mean energy 1.3539538647 eV (0.220064% error);
printed-interval weighted EEPF L1 0.015584. Four transport moment
errors are all <0.30%. These values do NOT extend to Examples 1–3.

## Traceability and remaining gates

- Original LXCat SHA-256: b8b1ff807d0586795dcabf4511a2a44b8b04828626b45e0fd95a319817c01063.
- Actual BOLSIG+ Example 4 output SHA-256: aa6c7c0ce00c61095934defa70f40e415474562b5e3e53374766c1ab7d6912d3.
- GitHub-built C++ binary SHA-256: ab12479cbbe6e3a485e579999fd442a9c0cd90ffbdacbafe7c5da1fb6e3072dd.
- Analysis outputs supplied separately: 151-condition JSON+CSV status inventory,
  142 C++-generated EEPFs, four-panel status visualization, sweep curves,
  and runnable local analysis code. **No third-party raw table
  or original BOLSIG+ EEPF rows are redistributed.**

Required next: obtain all three native reference outputs, audit their
run axes / Emax / EEPF export semantics, implement/validate nonzero
omega/N AC and automatic low-energy grids, verify Example 3 quadratic
spacing, and review Example 4 O2 three-body attachment density units.

Scientific status **HOLD_ALL_EXAMPLES_NATIVE_PARITY**. PR stays Draft;
main and existing production Oxygen ICP coefficients remain unchanged.
