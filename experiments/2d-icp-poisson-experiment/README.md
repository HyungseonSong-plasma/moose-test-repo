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

with `n_i,frozen = 1e16 1/m^3`, `epsilon_r = 1`, and `phi=0 V` on the
complete boundary of the plasma subdomain.

This is deliberately a one-way Poisson discriminator. The solved potential is
not yet used by electron drift, Joule heating, or the particle/energy wall
collection laws. Those remain identical to the qualified parent case.
