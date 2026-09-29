# Issue #357 — current 10 mTorr Oxygen state on real ICP geometry

This experiment is the first bounded geometry transplant after the frozen-heavy
Gummel qualification.

It uses the canonical real-QVT RZ reactor mesh and the current Physics object
assembly with solved electron particle transport, solved electron energy,
solved Poisson feedback, Oxygen heavy transport, and the admitted volumetric
chemistry ledger.

For this first volume discriminator the electron-energy equation is explicitly

```text
accumulation
+ diffusion
+ electrostatic energy drift
+ local Joule work (-E.Gamma_e)
+ elastic / inelastic / reaction energy sources
```

Electron particle/energy wall transport remains closed in this first bounded
volume test. Final wall/sheath/SEE closure is a later gate.

The transplanted operating state is:

- pressure: 1.333223684 Pa (10 mTorr)
- heavy temperature: 300 K
- electron reference density: 1e16 m^-3
- electron energy reference: 5.73276 eV
- O2 mass fraction: 0.99994
- O2s/O2p/O/Om/Op/Os: 1e-5 each
- accepted real-QVT 20 sccm flow topology retained
- timestep: 5.6650790022617894e-11 s
- 8 steps

The heavy transport file staged by the real-QVT source must be byte-identical
to the current canonical Physics Oxygen transport file. The real-QVT
electron_moments.txt is used for scientific transport; the 3-point CI smoke
table is explicitly rejected.

Outputs include elementwise RZ fields and 12-bin radial/axial averages for
electron density, mean electron energy, potential, charge density, charged
Oxygen mass fractions, electron mobility, and electron diffusion.

Temperature ownership is single-valued:

- `T_g` is the heavy/neutral gas temperature.
- There is no independent fixed electron-temperature state in the active model.
- `T_e` is derived from solved `mean_en_solved` as
  `T_e[K] = (2/3) mean_en_solved[eV] e/k_B`.
- The historical fixed `T_e = 20000 K` path is removed from charged-heavy
  Debye-Huckel transport for this experiment.

This is a solved-energy profile-sanity experiment. It does not claim a complete
ICP model: coil electromagnetic power deposition and final wall/sheath/SEE
validation are outside this first geometry transplant.
