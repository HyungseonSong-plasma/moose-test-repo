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

The initial state is uniform and quasi-neutral:

```text
n_e(t=0)     = 1.0e16 1/m^3
n_ion_fixed  = 1.0e16 1/m^3
electron mean energy = 5.73276 eV
phi(t=0)     = 0 V
```

The ion density remains fixed in time. Electron transport and wall losses create
charge separation; Poisson returns the resulting electrostatic potential.

## Electron boundary condition

On the named physical plasma boundaries, the electron particle equation uses
`PhysicsFVElectronGroundedSheathCollectionBC`: thermal electron collection with
grounded-sheath suppression based on local plasma potential and mean electron
energy.

The electron-energy equation uses
`PhysicsFVElectronGroundedSheathEnergyBC` in `physical_eV_state` mode, so the
same collected electron population carries energy out through the sheath.

The symmetry axis has no explicit boundary condition.

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

- real QVT/ICP RZ plasma geometry
- uniform quasi-neutral electron/fixed-ion initial state
- axis has no explicit boundary condition
- all named physical plasma boundaries are grounded for Poisson
- electron particle BC = thermal collection + grounded sheath suppression
- electron energy BC = sheath energy loss
- chemistry is OFF
- gas pressure and temperature are fixed at 1.333223684 Pa and 300 K
- pseudo timestep is fixed at 5e-11 s for 20 steps

This first case is intended to validate sibling execution, charge sign, Poisson
profile, sheath-driven electron depletion, and fast-state relaxation before
adding chemistry, adaptive pseudo-time, or evolving ions.

## Run

From this directory with the Physics executable:

```bash
physics-opt --check-input -i driver.i
physics-opt -i driver.i
```

Inspect `electron_energy_out.e`, `electron_energy_out.csv`, `poisson_out.e`, and
`poisson_out.csv`.
