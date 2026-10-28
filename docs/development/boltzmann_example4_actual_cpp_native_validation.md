# Actual 47-process BOLSIG+ Example4: repository C++ binary vs native (2026-10-28)

## Actual execution provenance — not a synthetic surrogate

The exact stand-alone `boltzmann_candidate_export.C` executable was compiled
by GitHub Actions **on PR #408's development branch**, in the new CI
`boltzmann-candidate-local-private-input` artifact, downloaded to a
private analysis environment, and its binary SHA-256 and the CI SHA256SUMS
were verified before running it. No original or derived LXCat table bytes
were uploaded to GitHub. This is an **actual run of the repository C++ code**
against the rights-controlled real source, separate from the earlier
independent Python reconstruction.

- Original source SHA-256:
  `b8b1ff807d0586795dcabf4511a2a44b8b04828626b45e0fd95a319817c01063`.
- Original BOLSIG+ 07/2024 native output SHA-256:
  `aa6c7c0ce00c61095934defa70f40e415474562b5e3e53374766c1ab7d6912d3`.
- Explicit 47-process local selection SHA-256:
  `daf82ef4927fabec32bed5b5b19214b432f580931518d21e1aa6d3a438751bac`.
- C++ binary before transport change, verified SHA-256:
  `0d76050612a4b021408e9327fe1c06ceb0250274bb7f7d9a73e3ac670936d90b`.
- C++ binary after M7c complete-momentum transport change, verified SHA-256:
  `ab12479cbbe6e3a485e579999fd442a9c0cd90ffbdacbafe7c5da1fb6e3072dd`.
- Input mixture 70% Ar / 20% He / 8% N2 / 2% O2; 10 Td, Tg=300K,
  Emax=15.8367 eV; C++ **uniform** 200 cells.
- Invocation (run only with the verified private source bytes):
  `boltzmann-candidate-example4 PRIVATE_SELECTED_47_SOURCE SOURCE_SHA256 10 300 15.8367 200 Ar=0.7 He=0.2 N2=0.08 O2=0.02 --bolsig-2024-boundaries --solve-coupled-temporal-growth --report-coupled-growth-transport`.
- C++ JSON retained all 47 source identities and listed explicitly
  the two inactive He reactions (19.8 eV excitation, 24.58 eV ionization).

## Direct comparison results (genuine input, genuine compiled C++)

| Observable | Native BOLSIG+ 07/2024 | Repository C++ candidate | Absolute relative difference |
| --- | ---: | ---: | ---: |
| Mean energy | 1.356940 eV | 1.3539538647 eV | **0.220064%** |
| Weighted ionization / reduced net growth | 4.33539e-24 m³/s (ionization) | 4.2924536921e-24 m³/s (net growth) | **~0.990%**, not identical quantities |
| Mobility × N | 4.37845e24 | 4.3857805995e24 | **0.167425%** |
| Diffusion × N | 5.69399e24 | 5.6959013838e24 | **0.033568%** |
| Energy mobility × N | 6.14584e24 | 6.1641402869e24 | **0.297767%** |
| Energy diffusion × N | 5.83169e24 | 5.8337569929e24 | **0.035444%** |

All four transport values are calculated **in C++**, using the
growth-corrected EEPF and the M7c complete first-harmonic momentum
scattering. They independently match the separately reconstructed
Python transport integrals to floating-point precision.

- C++ full generalized eigen residual: `1.30915e-14`; 7 iterations.
- C++ EEPF printed-interval number-mass-weighted L1 vs native: `0.0155840855`.
- High-energy tail-to-peak f0 ratio: `8.9863e-12`.
- 41 positive native inelastic/particle-changing rates aligned by ordered
  source identities: median relative difference **0.990747%**, largest
  **7.94891%** at tiny near-Emax Ar ionization (C3, native
  `3.11552e-29 m³/s`). Two He zero-rate processes are tracked explicitly;
  no missing/zero rate is included in the positive-rate statistics.

### Native C++ grid sensitivity at fixed actual Emax

| Uniform cells | Mean energy (eV) | Printed-native EEPF weighted L1 | Growth coefficient (m³/s) |
| ---: | ---: | ---: | ---: |
| 100 | 1.3602338195 | 0.0308325 | 4.52267160e-24 |
| 150 | 1.3556856821 | 0.0210908 | 4.35093716e-24 |
| 200 | 1.3539538647 | 0.0155841 | 4.29245369e-24 |
| 256 | 1.3531199283 | 0.0119934 | 4.26139338e-24 |

The full-sample L1 disagreement decreases with grid refinement.
Matching native mean energy at 150 cells is partly accidental;
native BOLSIG+ uses an automatically adapted mesh, whereas the C++
development candidate uses a uniform mesh. A resolution-dependent
difference remains: this is not an asymptotic grid-convergence certificate.

## Acceptance and unit/physics limitations

**Scientific acceptance remains HOLD_REAL_COLLISION_PROCESS_EQUIVALENCE**
despite the close numerical result.

1. The retained O2 3-body-labelled attachment record is used
   `as-tabulated-unscaled` because that reproduces the native output
   rate ledger. Its physical gas-density conversion remains unresolved
   and must be validated independently; the original other O2 two-body
   attachment was not in the reference run's 47 selected processes.
2. The C++ uniform grid does not reproduce BOLSIG+ automatic energy mesh.
3. M7c reports `growth_eepf_transport_diagnostic` separately from
   production transport tables; full spatial density-gradient /
   nonlocal transport assumptions require further parity work.
4. This does not validate arbitrary gas mixtures, RF models, electron-
   electron collisions, excited-state population models or production
   table substitution.
5. Full open-source/original source collision table licensing remains
   controlled. Neither source nor selected process tables are committed.

This evidence resolves the old gate "actual C++ 47-process execution
unavailable", **but not** the final physical model parity/production gate.
PR remains Draft, and main and the existing Oxygen ICP production
coefficients must remain unchanged.
