# Issue #402 — Charge assembler retirement and remaining Native gates

**Current status (2026-11-12):** The redundant
`PlasmaChargeTransportMaterial.C/.h` implementation and its
`PhysicsPlasmaChargeTransportMaterial` factory alias have been **removed**
from the unmerged Draft PR #523 branch. This retirement does **not** certify
full S6-417/941 input compatibility or P3 science acceptance.

## Final responsibility split

- `DDMaterial`: canonical `<species>_mobility` and
  `<species>_diffusivity`; constant, lookup, or AD-Functor input modes.
  Raw archival S6 source names such as `ion_mobility` must still be
  bridged to the canonical species names in scratch/generated input.
- `PhysicsPlasmaChargeDensityMaterial`: `ion_number_density_<id>`,
  `charge_number_density`, `charge_density`,
  `poisson_charge_source` (**AD Functor**). No mobility/diffusivity.
- FEM/FV transport Kernels: evaluate `E=-grad(phi)`, diffusion and
  signed drift at their own interpolation locations. The heavy-species
  FV correction Kernel reconstructs mass-conservative correction flux
  directly from charged-ion mobility and mass fractions.

Removed as redundant Material outputs: `electric_field`,
`electric_field_magnitude`, `rho_w_<id>`,
`rho_diffusivity_<id>`, `ion_drift_velocity_<id>`,
`electron_drift_velocity`, `heavy_mass_correction_velocity`,
`ion_mass_fraction_sum`, `neutral_remainder_mass_fraction`.
The names are **not** silently recreated in `DDMaterial`.
Consumers needing an independent diagnostic must request an explicit
provider and prove it does not change FV face-flux semantics.

## Poisson caveat — not automatically connected across discretizations

- **Legacy FV**: a separately generated `poisson_charge_source` is
  consumed by `FVCoupledForce` (e.g. historical Issue1 self-consistent
  2D input). The new charge-density Material can supply that Functor.
- **Current FEM `PoissonEq`**: `charge_source_material` is an optional
  `MaterialPropertyName` and activates a `MatBodyForce` plus `Diffusion`
  pair for the existing `fem_potential` variable. This path does **not**
  consume the `poisson_charge_source` AD Functor automatically.
  With no `charge_source_material`, the Physics reuses/creates the
  potential state only; it does not generate a sourced Poisson equation.
  An explicit FE Material Property producer or a separately validated
  Functor-to-FE source adapter is required for that activation.

## Pending acceptance gates

1. Exact-head Native P1 rebuild and P2 input validation for the positive
   three-ion DDMaterial + charge-density fixture and the retired factory
   negative case.
2. Validate both S6-417 and S6-941 staged Native ten-layer inputs and
   any legacy material type tokens; all physical source names are preserved
   in archives. Missing canonical ion bridges must fail closed.
3. Verify FE/FV Poisson RHS **source, scale, sign and solver ownership**;
   do not treat Functor publication as automatic FEM Poisson wiring.
4. FV face drift, diffusion, heavy correction, species/charge conservation
   and AD Jacobian comparison before scientific equivalence claims.
5. Operator-authorized P3 is separate: `SCIENCE_HOLD / P3 NOT_RUN / no merge`.

See `2026-11-12_issue402_ddmaterial_charge_flux_consumer_trace.md`.
