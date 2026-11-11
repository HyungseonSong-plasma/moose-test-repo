# Public 400 W electron-density reference profiles

Two frozen, public CSV tables are intended as **descriptive comparison
references** for 400 W Native runs. They are not an acceptance criterion.

| File | Geometry | Points | CSV SHA-256 |
| --- | --- | ---: | --- |
| `reference_vertical.csv` | r=0 cm, z=0..44 cm at 1 cm | 45 | `24f72104a12c087c36ec5107fb4c581276ffe110ee01b7d9fea48ab058eb9ad8` |
| `reference_horizontal.csv` | z=23 cm, r=0..25 cm at 0.5 cm | 51 | `8e6856a46273b00058428874d3bcbe89dadddd0038e803565c8dfab1c220eff8` |

Fields: first coordinate column in cm; `n_e_m^-3` is electron number
density in m^-3. Peak reference value is 8.885e16 m^-3.

## Source and limitations

The values are direct two-column projections of the user's original
library-derived CSV profiles:
`HPEM_400W_reference_axis_vertical_slice_m-3.csv` and
`HPEM_400W_reference_z23cm_radial_slice_m-3.csv`, both produced from
the archived 400 W matrix `E_matrix(2).dat`. This origin is recorded
for scientific provenance only; plot labels and general workflow names
use `Reference`, `Vertical`, and `Horizontal`.

The source matrix's original physical timestamp is **unknown**.
Its coordinate convention is assumed (r = 0..25 cm, z = 0..44 cm) and
has not been independently calibrated. Zero values at the matrix
boundaries are retained exactly; **do not infer physics outside the
Native plasma mesh**. The two public CSVs do not prove that the original
source matrix has been independently reverified.

No original protected rates, private raw simulation artifacts, or secrets
are part of these reference tables. Changes to these inputs require a
reviewed commit and updated SHA-256 checks. Every comparison records the
exact input file hashes and Native Exodus/CSV hashes, and keeps
`SCIENCE_HOLD` until independent scientific validation.
