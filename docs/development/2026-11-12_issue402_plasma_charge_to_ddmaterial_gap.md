# Issue #402 — PlasmaChargeTransportMaterial → DDMaterial replacement gap

**Status: ION COEFFICIENT ALIASES MOVED; WHOLE CLASS REPLACEMENT NOT COMPLETE (2026-11-12).** DDMaterial is now the canonical alias publisher, and PlasmaChargeTransportMaterial no longer registers mobility/diffusivity outputs. The original charge-core class still provides separate derived diagnostics. Full S6-417/941 Native P3 activation and scientific parity remain open.

## Already implemented

- `DDContinuityEq::addFunctorMaterials()` creates one `DDMaterial` for
  each selected FEM/FVM species with a JSON `drift_diffusion` entry.
- JSON `model=functor` derives the upstream
  `<species>_mobility` and `<species>_diffusivity` AD Functors;
  `model=constant` requires numerical values, `model=lookup`
  uses a transport table. `DDMaterial` does not register duplicate
  aliases when another provider owns these canonical Functors.
- S6-417/S6-941 **review-only** merged JSONs select `model=functor`
  for O2p/Om/Op. This is not yet the activated ten-layer Native P3 deck.

## Still owned by PlasmaChargeTransportMaterial

The old charge-core implementation must be functionally migrated with
matching units, AD derivatives, signs, ion ordering and names:

| Existing published Functor | Contract / required migration |
| --- | --- |
| `electric_field`, `electric_field_magnitude` | `E=-grad(phi)`, norm |
| `rho_w_<ion>` | `rho * w_i` |
| `ion_number_density_<ion>` | `rho*w_i*N_A/M_i` |
| `rho_diffusivity_<ion>` | `rho*D_i` for FV mass-fraction equation; **not** `D_i` |
| `ion_drift_velocity_<ion>` | `z_i*mu_i*E` |
| `electron_drift_velocity` | `-mu_e*E` |
| `heavy_mass_correction_velocity` | `-sum_i(w_i*z_i*mu_i)*E` |
| `ion_mass_fraction_sum`, `neutral_remainder_mass_fraction` | sum and remainder |
| `charge_number_density`, `charge_density` | `sum_i(z_i*n_i)-n_e`, multiplied by elementary charge |

These derived terms are **not** currently implemented in `DDMaterial`.
Their consumers (including heavy FV transport, charge/Poisson, electrostatic
drift and diagnostics) cannot simply lose the original Material.

## Replacement acceptance gates

1. Define the DDMaterial/DriftDiffusion ownership for the *whole charge
   core*, not merely per-species mu/D. Multi-ion mass fraction, density,
   molar mass, charge, potential and electron density inputs need explicit
   source contracts in generated backend JSON or canonical state naming.
2. Implement the old charge-core Functors in DDMaterial or a subordinate
   internally generated charge-core DDMaterial, with no duplicate producers,
   self-referential coefficient lookups or broken legacy aliases.
3. Migrate every direct `type=PlasmaChargeTransportMaterial` and
   `type=PhysicsPlasmaChargeTransportMaterial` input in **scratch only**;
   retain old Native archives for baseline comparison.
4. Run exact-head native `--check-input` for **both S6-417 and S6-941**
   with all ten source layers, plus AD derivative, charge balance, ion
   drift, heavy correction and RF/Joule/Poisson/FV regression.
5. Remove or alias the old C++ class **only after** source/provider parity
   and all live consumers are confirmed on DDMaterial. P3 science
   and verified durable artifact receipts remain separate gates.

No physical input, numerical coefficient or original archived deck is
changed by this gap analysis. **SCIENCE_HOLD; P3 NOT_RUN.**

See `2026-11-12_issue402_ddmaterial_charge_flux_consumer_trace.md` for the source-to-FV usage trace. The new `charge_core_ddmaterial_owner_p2.i` fixture proves a three-ion raw-source bridge with the legacy charge Material present; it does not replace full S6 exact-head P2.
