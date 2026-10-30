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

Selection and stoichiometric checks alone are NOT a runnable 24-source
ICP case. Source projection for the other unimplemented chemistry channels,
the unresolved EI-413/EI-414 O2* effective excitations, and the actual
400/1000 W physics-opt runs remain pending; never claim density curves
from this gate.
