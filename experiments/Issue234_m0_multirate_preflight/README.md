# Issue 234 M0 — multirate characteristic-time preflight

This stage derives the heavy-parent and fast-electron timestep bracket from the governed Issue-228 snapshot and the active transport implementation.

It does **not** construct or validate a MultiApp yet. Its role is to make the timestep choice reproducible before M1 implementation.

Planned bracket:

- heavy candidate: `1e-8 s`
- heavy reference: `5e-9 s`
- electron candidate: `1e-11 s`
- electron reference: `5e-12 s`
- electron coarse controls: `2e-11 s`, `1e-10 s`

The production values remain provisional until M1/M2 convergence and M3 monolithic-vs-multirate equivalence pass.
