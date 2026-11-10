# Independently calculated S6 Boltzmann electron-impact rates

This directory contains the **19 independent new Boltzmann lookup tables** used
for experimental S6 comparisons in Issue #493. These tables are **not** the
original protected S6 rate tables, nor a copy or interpolation of MCS.OUT data.
They do not represent accepted scientific parity with original reactions.

- Source: independent 100-state Boltzmann calculations spanning **4–1200 Td**
  for the S6 initial neutral composition; the mean electron energy varies from
  **0.47634066574714 to 19.24235027551 eV**.
- File format: two whitespace-separated floating-point columns without header.
  Column 1 is the **mean electron energy in eV**; column 2 is the **MOOSE raw
  reaction coefficient in m³/(mol·s)**.
- Conversion: `k_MOOSE = N_A × k_physical` with
  `N_A = 6.02214076e23 mol⁻¹`; the underlying physical coefficients are
  `m³/s`. Never substitute physical `m³/s` data directly for these MOOSE
  coefficients; the source term would be wrong by a factor of `N_A`.
- Each file contains **100 finite, non-negative values**, on a strictly
  increasing common electron-energy grid. The new values were checked against
  an independent 19-channel calculation export and the experiment-package
  SHA-256 manifest before publication.
- These are **research candidate** tables. S6-417 and S6-941 baseline A is an
  archived run; using these tables for B/C does not constitute scientific
  acceptance. `SCIENCE_HOLD` remains in force until the native P2/P3/P4 gates
  and independent physical-field checks are complete.
- The original S6 protected coefficients, comparison MCS data, raw private
  solver traces, and restricted experimental package are **not stored here**.

When using the tables, point experimental input lookups explicitly at this
`boltz/` directory. Do not overwrite or silently replace the original
`physics_app/data/electron_impact/` reference data or production defaults.
