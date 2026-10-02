# 2d-icp-poisson-experiment

Candidate reusable **Poisson** layer built directly on
`electron-diffusion-energy-experiment`.

The electron particle and electron-energy equations, transport lookup,
wall-loss closures, mesh, timestep, and initial state are unchanged. The new
equation is

```text
-div(epsilon_r grad(phi)) = rho_q / epsilon_0
rho_q = e * (n_i,frozen - n_e)
```

with `n_i,frozen = 1e16 1/m^3` and `epsilon_r = 1`. The `phi=0 V`
Dirichlet condition is applied only to the eight physical plasma surfaces:
`inlet`, `outlet`, `plasma_electrode`, `plasma_metal`,
`plasma_right`, `plasma_cover`, `plasma_wafer`, and
`plasma_focus_ring`.

For this RZ model (`rz_coord_axis = Y`), `x=0` is the symmetry axis. It is
not a physical boundary and receives no explicit wall, sheath, electrode, or
Dirichlet BC. The axis is left to the RZ regularity/natural zero-normal-flux
semantics.

This is deliberately a one-way Poisson discriminator. The solved potential is
not yet used by electron drift, Joule heating, or the particle/energy wall
collection laws. Those remain identical to the qualified parent case.
