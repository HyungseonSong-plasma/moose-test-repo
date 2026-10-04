# Fixed-ion electron-energy / Poisson prototype

This is a deliberately minimal partitioned plasma prototype. It does not use
`GummelIterationAction`, fixed-point convergence objects, heavy-ion evolution,
or heavy-mass electromigration correction.

## State

Electron sibling:

- `n_e` : physical electron number density [1/m^3]
- `electron_energy` : electron energy density [eV/m^3]
- `potential_from_poisson` : transferred Poisson potential

Poisson sibling:

- `potential`
- `n_e_from_electron` : transferred electron density
- `n_ion_fixed` : temporally frozen positive-ion number density

The initial profiles satisfy

```text
n_ion_fixed(x) = n_e(x, t=0)
```

so the initial charge density is locally zero. The ion profile remains fixed in
time. Electron diffusion, electrostatic drift, energy transport, and Joule
heating then create the nontrivial electron/Poisson feedback.

## Coupling order

One parent pseudo step is

```text
phi^k
  -> electron + energy solve
  -> n_e^(k+1)
  -> Poisson solve with fixed n_i
  -> phi^(k+1)
```

There is exactly one electron-energy solve and one Poisson solve per pseudo
step. There is no inner Gummel/fixed-point loop.

The sibling solves are staggered because the pinned MOOSE version executes
sibling BETWEEN_MULTIAPP transfers before MultiApps on a given execution flag:

- electron-energy: `TIMESTEP_BEGIN`
- Poisson: `TIMESTEP_END`

## Initial numerical scope

- RZ real-QVT plasma mesh
- axis has no explicit boundary condition
- all named physical plasma boundaries are grounded for Poisson
- electron/energy external drift flux is disabled on the physical boundaries
- chemistry is OFF
- electron wall collection / sheath BC is OFF
- gas pressure and temperature are fixed at 1.333223684 Pa and 300 K
- pseudo timestep is fixed at 5e-11 s for 20 steps

This first case is intended only to validate the new sibling architecture,
charge sign, Poisson profile, and fast-state relaxation before adding chemistry,
wall losses, adaptive pseudo-time, or evolving ions.

## Run

From this directory with the Physics executable:

```bash
physics-opt --check-input -i driver.i
physics-opt -i driver.i
```

Inspect `electron_energy_out.e`, `electron_energy_out.csv`, `poisson_out.e`, and
`poisson_out.csv`.
