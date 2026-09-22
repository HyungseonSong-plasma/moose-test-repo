# Issue 306 heavy-charge motion discriminator

This experiment layers heavy motion onto the accepted Issue #253 Sequence-12
fast subsystem without changing the fast electron/Poisson/energy/Joule/O2
elastic model.

Matrix:

- heavy state: frozen vs released;
- heavy timestep: chi_h = 40;
- heavy cycles: 2;
- common final time: 80 initial dielectric-relaxation times;
- fast timestep: chi_e = 1, 10, 20;
- fast subcycles per heavy interval: 40, 4, 2.

Released-heavy parent physics:

- 1D heavy flow;
- right 20 sccm pure-O2 inlet;
- left absolute-pressure outlet;
- six solved Q-1 heavy mass fractions;
- mixture-averaged diffusion;
- electrostatic drift for O2+, O-, and O+;
- heavy mass-frame electromigration correction;
- no volumetric chemistry and no RF heating.

The outlet pressure is kept at the Sequence-12 gas-state value (0.66661 Pa)
while reusing the previously validated inlet/outlet BC topology.  This avoids
changing the fast gas state at the same time as heavy motion is enabled.

Coupling order per heavy interval:

1. advance the heavy parent with the previously returned fast potential;
2. at parent TIMESTEP_END transfer updated O2+/O-/O+ to the fast child;
3. subcycle the unchanged Sequence-12 fast child to the parent time;
4. transfer potential, electron density, and mean energy back to the parent.

The frozen control uses the same parent clock and the same nested fast child,
but the heavy parent is a no-solve state carrier.  Therefore frozen/released
pairs at the same chi_e have byte-identical fast-child inputs.

The aggregate reports raw potential differences, offset-removed shape error,
E-field error, electron-density and mean-energy errors, net-charge error, and
the released/frozen potential-offset contraction ratio.  It does not assign a
terminal physical interpretation automatically.


## Sequence 02 — COMSOL-style left charged-heavy wall loss

Sequence 01 demonstrated that two heavy cycles with bulk transport alone leave
the charged-heavy state close to frozen.  Sequence 02 keeps the same clocks
(`chi_h=40`, two heavy cycles, `chi_e=1/10/20`) and compares:

- `bulk`: the successful Sequence-01 released-heavy topology;
- `wall`: the same topology plus left-wall loss for O2+, O-, and O+.

The wall case uses the current production `PhysicsIonWallFluxMaterial`:

```text
Gamma_surface   = s * 0.25 * n_i * v_th
Gamma_migration = n_i * mu_i * max(z_i * E_n, 0)
Gamma_wall      = Gamma_surface + Gamma_migration
```

with `sticking=1` for O2+, O-, and O+.  Bulk electrostatic drift and the
heavy-mass electromigration correction continue to avoid both external
boundaries, so the left migration flux has a single owner.

The left `INSFVOutletPressureBC` remains only as the constant-density
hydrodynamic pressure reference.  It is not the heavy-species boundary
condition in the wall case.  This distinction is required because removing
the only pressure anchor while retaining the right mass-flow inlet would make
the present incompressible 1D flow closure ill-posed.

Sequence-02 evidence must therefore be interpreted as a charged-heavy
wall-loss discriminator, not as a fully resolved solid-wall hydrodynamic
model.


## Sequence 03 — left inlet / right COMSOL charged wall

Sequence 03 fixes the boundary topology to:

```text
left:
  20 sccm pure-O2 inlet
  solved charged-heavy inlet fluxes = 0

right:
  hydrodynamic pressure reference
  electron particle wall loss
  electron energy wall loss
  charged-heavy wall loss
```

Electron wall ownership remains **right-only**. The accepted fast child already
uses the COMSOL drift-diffusion thermal particle coefficient,

```text
Gamma_e,wall = 0.5 * n_e * v_e,th
```

and the electron-energy BC uses the COMSOL coefficient `5/6`. The shared
`PhysicsElectronWallPhysics::absorbingNumberFlux` helper was also aligned to
the same `0.5` convention.

For charged heavy species on the right wall:

```text
O2+, O+:
  surface loss   = n_i * u_B
  u_B            = sqrt(e * N_A * T_e[eV] / M_i)
  migration loss = n_i * mu_i * max(z_i E_n, 0)

O-:
  surface loss   = 0.25 * n_i * v_th,i   (sticking = 1)
  migration loss = n_i * mu_i * max(z_i E_n, 0)
```

Bulk electrostatic drift and heavy-mass electromigration correction continue to
avoid both external boundaries, so the right-wall migration flux has a single
owner.

A same-topology thermal-ion control is retained, where O2+/O-/O+ all use
thermal sticking plus migration. This isolates the positive-ion
thermal-to-Bohm replacement.

### Governed evidence

```text
workflow run = 35703377359 / SUCCESS
exact source = 6a547da25ba4d33fcb455542e8972bbd722b443e
manifest     = automation/manifests/experiments/Issue_306_experiments03.json

P0 PASS
P1 PASS
P2 PASS
P3 PASS
```

All six `thermal/comsol x chi_e={1,10,20}` cases converged at
`chi_h=40`, two heavy cycles, and common `T=80 tau_epsilon(initial)`.

The Bohm replacement materially changes the absolute potential level while
leaving the offset-removed field/profile shape almost unchanged over this
short horizon. For example, COMSOL-vs-thermal mean-potential shifts are about
`-0.500 V` for all three electron chi values, while the corresponding
electric-field relative differences are only O(`1e-6`). This is a wall-law
effect and must not be confused with electron-timestep sensitivity.
