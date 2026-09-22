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
