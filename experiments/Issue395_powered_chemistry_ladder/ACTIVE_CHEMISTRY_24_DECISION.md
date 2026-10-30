# Oxygen ICP 400/1000 W: active chemistry decision

2026-10-30 user decision: **exclude EI-936** from the current powered ICP
research chemistry, and keep the original 25-row registry untouched as
scientific provenance. Do not mistake reactant O(3P) for product O(1S).

## Species identity (existing MOOSE variables)
- O(3P) = O, `w_O`
- O(1D) = Os, `w_Os`
- O2(a1Delta_g) = O2s, `w_O2s`
- O2(X) = O2, `w_O2_constraint`

The corresponding registry reactions EI-935 (e+O -> e+Os) and EI-943
(e+Os -> e+O) remain selected.

## Reaction counts
- Original registry: 25 reactions (22 electron-impact, 3 heavy)
- Active experimental selection: **24 reactions**
- Active electron-impact rate lookups: **19**
- Formula rates: 2, heavy reactions: 3
- EI-936 is disabled, including all species progress and electron-energy loss.

**Safety:** DO NOT rewrite EI-936 as e + O -> e + Os, and DO NOT add its
rate to EI-935 or assign O(1S) to the Os variable. Original 25-row
scientific inventory remains available for provenance.

## User-selected EI-407/413/414 effective O2(a) lump

For the 400/1000 W ICP research case ONLY:
- EI-407, EI-413 and EI-414 retain distinct 100-point lookup rate owners.
- All three reactions convert O2(X) -> O2(a1Delta_g), solver species **O2s**.
- Combined molar production rate: R_EI407 + R_EI413 + R_EI414.
- O2s mass source: +0.032 * (R407+R413+R414) kg/(m3 s).
- Constrained O2(X) mass sink: -0.032 * (R407+R413+R414) kg/(m3 s).
- Electron particle source: zero for all three.
- Electron energy source: -(0.977 R407 + 8.4 R413 + 10.0 R414).
- The earlier O2star active-product placeholder is retired for these 2
  channels; it remains in the immutable source inventory for provenance.
- This **does not validate the microscopic branching** of Phelps 8.4/9.97-eV
  loss channels into actual O2(a1Delta_g). This is a user-selected surrogate.

The executable overlay generator is
`build_lumped_o2a_ei407_413_414.py`. The private 100-point lookup files
are NOT in the public repo; provide them through `--rate-dir` at build time.

Selection, stoichiometry, and standalone overlay tests do not make a complete
24-source ICP case. Coupling other chemistry channels and real 400/1000 W
`physics-opt` --check-input/transient runs remain pending. Do not claim
density trends from this gate.
