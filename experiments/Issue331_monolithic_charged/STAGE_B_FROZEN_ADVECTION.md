# Stage-B frozen-neutral advection realization

## Finding

The accepted Sequence08 charged-heavy advection owner cannot be copied unchanged into the frozen-neutral monolithic charged prototype.

`PhysicsFVMassFractionAdvection` derives from `INSFVScalarFieldAdvection` and obtains the bulk velocity through the INSFV Rhie-Chow path (`velocity()`). In the accepted released-heavy parent that path is supplied by nonlinear `u`, `p`, `INSFVRhieChowInterpolator`, and global Rhie-Chow parameters.

Stage B, however, requires the neutral-flow state to be read-only while the nonlinear unknown vector remains

`[log_e, n_epsilon, w_O2p, w_Om, w_Op, potential_plasma]`.

Therefore copying `PhysicsFVMassFractionAdvection` together with nonlinear `u,p` would violate the Stage-B ownership discriminator, while deleting the advection term would violate accepted #306 physics.

## Required realization

For Stage B only, realize the same conservative charged-heavy convective flux

`rho * (u_neutral . n) * w_k`

with `rho` and `u_neutral` supplied as read-only AD functors/fields from the frozen same-time neutral baseline. The transported mass fraction remains the nonlinear charged unknown and uses the same accepted FV interpolation/upwinding semantics.

This is a representation/ownership adapter, not a new physical term. It must not alter:

- the accepted neutral velocity state;
- mixture density used by the charged-heavy equation;
- advected interpolation semantics;
- diffusion, electrostatic migration, mass-frame correction, wall flux, or time derivative;
- the ordinary Poisson equation.

A thin `FVFluxKernel` analogous to `PhysicsFVElectrostaticDrift` is an admissible implementation if no standard MOOSE functor-advection object provides the same `rho*u*w` FV semantics. Before adding C++, perform a standard-capability census.

## Fail-closed gates

1. Do not retain nonlinear gas momentum/pressure merely to satisfy the old advection kernel; that would no longer be the requested frozen-neutral discriminator.
2. Do not set the convective flux to zero merely because the initial accepted velocity happens to be small/zero; the term and its baseline state must remain represented.
3. Do not replace the accepted flux by pure drift+diffusion.
4. The frozen velocity/density fields must have explicit provenance from the same-time accepted baseline used for the Gummel reference.
5. Stage C must show that the frozen neutral fields do not enter the charged Newton unknown set while charged residuals still couple to `potential_plasma` and Poisson still couples to every charged density.

## Next obligation

Census standard MOOSE FV advection objects for a read-only velocity-functor realization. If none preserves the accepted flux/interpolation contract, add the smallest Issue331-owned functor-velocity mass-fraction advection kernel with a positive equivalence test against `PhysicsFVMassFractionAdvection` on a prescribed velocity field. Only then assemble `monolithic_charged.i`.
