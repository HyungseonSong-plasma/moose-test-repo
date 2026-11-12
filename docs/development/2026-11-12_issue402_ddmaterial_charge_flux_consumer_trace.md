# Issue #402 — DDMaterial ion coefficient ownership / FV flux consumer trace

**Scope:** Draft PR #523, scratch/S6 P2 validation only. No P3 or
scientific B/D parity accepted. `SCIENCE_HOLD`.

## Code refactor: one canonical species mobility / diffusivity publisher

`physics_app/src/materials/PlasmaChargeTransportMaterial.C` no longer calls
`addFunctorProperty` for `<ion>_mobility` or `<ion>_diffusivity`.
It still takes its original `ion_mobilities` and `ion_diffusions`
input vectors and evaluates those source Functors in derived charge/flow
diagnostics. These inputs must not be removed until all dependent features
have a new owner.

`physics_app/src/materials/DDMaterial.C` now is the **only class in this
pair** that publishes canonical per-species mobility and diffusivity.
For legacy S6 raw sources, a DDMaterial in `model=functor` with
`mobility_source`/`diffusivity_source` set to the original Native Functors
publishes the canonical species aliases with unchanged AD derivatives and
**no numerical conversion**. For future backend JSON `{"model":"functor"}`,
those source names are *not* carried in the JSON; the existing Native
producer must supply the canonical names or the scratch input must
provide the DDMaterial raw-to-canonical bindings. Default canonical
`functor` mode consumes existing names and deliberately does not
register duplicate aliases. `model=lookup` and numerical
`model=constant` still publish coefficient Functors directly.

New synthetic input:
`experiments/Issue402_plasma_dsl_g1/charge_core_ddmaterial_owner_p2.i`
checks that all three canonical O2p/Om/Op pairs are published by
DDMaterial while a legacy `PlasmaChargeTransportMaterial` still
supplies derived charge/flux diagnostics. P2 uses artificial coefficient
values; no physical S6 data are replaced.

**Outstanding runtime gate:** the committed full S6-417/941 review JSONs
declare `model=functor`, but the actual Native ten-layer P3 staging
still uses common+variant Chemistry JSON without DD transport records.
The future backend-generated input must bind the original Native
coefficient Functor names exactly once (e.g. through a generated
DriftDiffusion-owned DDMaterial bridge) or rename their producer names
to canonical. Blindly activating the review JSON without a raw-source
bridge may leave unresolved `O2p_mobility`/etc. Do not mark full
S6 P2/P3 ready on the synthetic ownership smoke alone.

## Consumer trace

| Functor / derived quantity | Producer | What actual FV flux consumes |
| --- | --- | --- |
| `E = -grad(phi)` / `electric_field` | Legacy charged transport Material | `PhysicsFVElectrostaticDrift::computeQpResidual()` and `PhysicsFVHeavyMassElectromigrationCorrection::computeQpResidual()` each evaluate `-_potential.gradient(centered_face, state)` themselves, **not** `electric_field`. Preserve face interpolation / AD stencil. |
| `<ion>_mobility`, `<ion>_diffusivity` | DDMaterial after migration | Generated FEM log-molar Kernel consumes canonical coefficients; Native heavy FV kernels consume their own declared mobility/D Functor names, which still need input rewiring if canonical names change. |
| `ion_number_density_<ion>` | Legacy charged transport Material; separately `PhysicsPlasmaChargeDensityMaterial` can produce it | `n_i = rho*w_i*N_A/M_i`; no direct reference found in tracked heavy FV flux implementations. The charge source is recomputed in the charged-density Material, not derived by reading this published Functor. Never instantiate both producers on the same scope. |
| `rho_diffusivity_<ion>` | Legacy charged transport Material | `PhysicsFVMixtureAveragedDiffusion` evaluates `rho` and `diffusivity` separately and constructs `rho*D` at each FV face, including its interpolation options. It **does not** consume the named `rho_diffusivity_<ion>` Functor. |
| `ion_drift_velocity_<ion>` | Legacy charged transport Material | `PhysicsFVElectrostaticDrift` calculates `z_i*mu_i*(E.dot(normal))` at a centered face and chooses upwind state for the transported fraction; it **does not** consume this derived vector Functor. |
| `electron_drift_velocity` | Legacy charged transport Material | No direct consumer found in the tracked FV ion/heavy correction kernels; the electron equation has separate FEM drift operators. |
| `heavy_mass_correction_velocity` | Legacy charged transport Material | **Not consumed** by the accepted #15 Path-B FV flux path. That path explicitly forbids this name as a slip velocity and instead constructs a conservative correction at the face. |

## Are neutral species corrected?

**Yes, in the accepted #15 Path-B heavy FV flux implementation.** The
`experiments/Issue15_charged_heavy_migration/prepare.py` source contract
requires exactly three direct charged-ion migration Kernels (O2p, Om, Op)
and **six** `PhysicsFVHeavyMassElectromigrationCorrection` Kernels
for independent solved heavy species `w_O2s, w_O2p, w_O, w_Om, w_Op, w_Os`.
That includes neutral `w_O2s, w_O, w_Os`.
The constrained O2 remainder is **not** a seventh independent equation.
The FV correction calculates a negative provisional charged-heavy
mass flux normal and multiplies by each corrected species face mass fraction.
Thus the *correction physics* applies to neutrals but the old
`heavy_mass_correction_velocity` *Functor* is not the numerical
implementation of that flux. This is a statement about the #15
accepted Path-B source; the S6-417/941 archived Native flux arrangement
requires its own exact staged-input check, not an inference from #15.

## Why retain the old Material at this stage?

It still publishes `electric_field`, `electric_field_magnitude`,
`rho_w_<ion>`, `ion_number_density_<ion>`,
`rho_diffusivity_<ion>`, `ion_drift_velocity_<ion>`,
`electron_drift_velocity`, `heavy_mass_correction_velocity`,
`charge_number_density`, `charge_density`, and mixture mass-fraction
diagnostics. Other charged-density Materials also publish some of these;
source exclusivity must be proven before moving or deleting them.
A second migration may eliminate unused diagnostics or relocate them,
but **do not** equate that with a successful flux-owner migration.

## Safety gates

- P1 exact-head compile and the new three-ion P2 smoke.
- P2 of the complete staged 417 and 941 inputs with canonical source
  bindings, no duplicate aliases, no missing raw Native Functors.
- FV face-by-face drift, diffusion and heavy correction equivalence,
  mass/charge conservation, and AD Jacobian comparison.
- No P3 dispatch, merge, or scientific promotion without separate approval.
