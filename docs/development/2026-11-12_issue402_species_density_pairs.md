# Issue #402 — Species/initial number-density pairs (Draft)

**Scope:** optional Physics-owned variable and IC construction in
`DDContinuityEq`; source only. No merger, P3 run or S6 science parity claim.

## Proposed input grammar

```ini
[Continuity]
  # Format: species_name initial_number_density ...
  # initial_number_density [1/m^3], finite and strictly positive
  fem_species = 'e 1e16'
  fvm_species = 'O2p 1e16 Om 1e14 Op 1e15'
  fem_potential = potential
[]
```

A quoted whitespace-delimited sequence alternates solver-safe species ID
and physical particle number density in `1/m^3`. The complete list for each
FEM/FV option must use **only** paired entries or **only** legacy species names.
Zero, negative, NaN, Infinity, out-of-range, malformed and unpaired numbers
are rejected; no hidden floor or arbitrary concentration is applied.

Physics creates `MooseVariable` (default FIRST/LAGRANGE) for `log_e`
and `MooseVariableFVReal` for `log_O2p`, `log_Om`, `log_Op`.
Initial conditions are `ConstantIC` / `FVConstantIC` and represent
`ln(n_0/N_A)`, where `N_A = 6.02214076e23 mol^-1`.
The two-log difference avoids underflow for small positive densities.
This is a log-*molar* state, NOT `ln(number_density)`.

To prevent a silent change to original S6 scientific conditions, the paired
form fails if a solver variable of the same name already exists. Use the
names-only legacy form `fem_species='e'`,
`fvm_species='O2p Om Op'` with externally defined variables/ICs for
historical staged sources. Do not mix both ownership modes for one variable.

This change does **not** define `log_e_energy`, `potential`, kinetic
rate Functors, FVM ion equations, or Maxwell/Poisson ownership. Those
remain separately owned and must be supplied as needed. The C++ source
provides the new form, with independent Native P1 build and P2 positive /
negative `--check-input` checks required before acceptance. Existing
S6-417/941 archived inputs, staged templates and parity gates are untouched.
