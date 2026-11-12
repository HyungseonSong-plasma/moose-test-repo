# Issue #402 — Charge and FV consumer trace after Material retirement

**Scope:** current unmerged Draft PR #523. P1/P2 pending exact-head
validation; `SCIENCE_HOLD`, P3 NOT_RUN.

## Coefficient / charge output ownership

| Functor | Live owner after migration | Actual consumer |
| --- | --- | --- |
| `<ion>_mobility`, `<ion>_diffusivity` | `DDMaterial` via Native raw source forwarding, lookup, or numerical constants | `FEMLogMolarDriftDiffusion` references canonical species names. Native FV flux Kernels still read names explicitly specified in their original `.i` and must be rewired separately if needed |
| `ion_number_density_<ion>` | `PhysicsPlasmaChargeDensityMaterial` | Charge bookkeeping, diagnostics, possibly ion-wall-flux components given explicit input binding; heavy FV transport does not consume the old output |
| `charge_number_density`, `charge_density`, `poisson_charge_source` | `PhysicsPlasmaChargeDensityMaterial` | FV Poisson `FVCoupledForce` can consume `poisson_charge_source`; `PoissonEq` FEM has different MaterialProperty interface |

No C++ `PlasmaChargeTransportMaterial` implementation or factory alias
remains. The three-ion positive P2 input
`experiments/Issue402_plasma_dsl_g1/charge_core_ddmaterial_owner_p2.i`
constructs three DDMaterial Functor forwarders and one separate
PhysicsPlasmaChargeDensityMaterial. The original raw S6 ion sources
must be bridged to canonical names **once**; JSON `model=functor`
deliberately does not carry arbitrary source names.

## Redundant derived outputs and actual FV execution

- **Electric field**: `PhysicsFVElectrostaticDrift` and
  `PhysicsFVHeavyMassElectromigrationCorrection` evaluate
  `E=-_potential.gradient(centered_face, state)` independently;
  FEM `FEMLogMolarDriftDiffusion` couples the potential gradient.
  `electric_field` and `electric_field_magnitude` outputs are not
  needed as intermediate Material Functors.
- **Ion drift velocity**: `PhysicsFVElectrostaticDrift` forms
  `z*mu*(E dot n)` and uses its sign for upwind interpolation.
  The deleted `ion_drift_velocity_<id>` vector was not read.
  `electron_drift_velocity` is similarly unnecessary:
  `FEMPlasmaTransport.C` consumes electron mu/D and gradient of phi.
- **Diffusion**: `PhysicsFVMixtureAveragedDiffusion` evaluates `rho`
  and `D` separately on each side/face to construct `rho*D`;
  the deleted cell/space Functor `rho_diffusivity_<id>` was not used.
- **Mass correction**: `PhysicsFVHeavyMassElectromigrationCorrection`
  reconstructs the *face normal* charged-ion mass flux and subtracts it
  from every corrected heavy-species equation. It does not read the old
  `heavy_mass_correction_velocity` vector; substituting a cell-based
  slip velocity would change upwind/interpolation semantics.
- **Other removed diagnostics**: `rho_w_<id>`,
  `ion_mass_fraction_sum`, `neutral_remainder_mass_fraction`
  were not required as named providers in tracked production FV flux
  implementations. The conserved mass/mixture closures are computed
  by their dedicated kernels or existing Native Functors.

## Neutral-species correction in accepted #15 Path-B

The immutable accepted #15 heavy FV input has three **direct** drift
Kernels (O2p, Om, Op) and six **mass correction** Kernels for
w_O2s, w_O2p, w_O, w_Om, w_Op, w_Os. Neutrals O2s, O, Os therefore
receive the conservative mass correction; O2 is a constrained remainder
rather than a seventh independently solved equation.
This is confirmed by
`tests/test_issue402_species_transport_rule.py`, **not** assumed
to establish S6-417/941 physical equivalence.

## Poisson interface distinction

`physics_app/src/materials/PhysicsPlasmaChargeDensityMaterial.C`
publishes the AD Functor `poisson_charge_source` =
`charge_density / eps_0`. The historical
`experiments/Issue1_reactor_o2plus_integration/self_consistent_2d/self_consistent_2d.i`
FV Poisson input explicitly sets `v = poisson_charge_source` on
`FVCoupledForce`.

`physics_app/src/physics/plasma/PoissonEq.C` instead accepts
`charge_source_material` as `MaterialPropertyName`, with
`MatBodyForce.material_property` and a FEM `Diffusion` Kernel.
It does **not** build an adapter from the charge AD Functor, and
omission of `charge_source_material` means no generated Poisson RHS.
Retiring the old charge assembler cannot and does not close this gap.

**Validation still required:** complete staged Native S6 P2; matching
RHS signs/scaling and avoiding duplicate charge producers; FV face/AD
parity; no P3 or merge without explicit operator authorization.
