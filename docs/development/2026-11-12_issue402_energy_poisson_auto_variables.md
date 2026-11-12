# Issue402: Physics-owned electron-energy and Poisson FEM state

**Draft. No P3, no merge, SCIENCE_HOLD.**

Poisson accepts `fem_potential`, replacing `potential_variable` with no
compatibility alias. A present FEM potential is reused without modifying
its initial condition. A missing potential is auto-created as `MooseVariable`
with `ConstantIC` initial numerical guess `initial_potential_V` (default
0 V, finite). The value is not a boundary condition. If `initial_potential_V`
is explicitly supplied for an external variable, reject that conflicting
ownership. Do not substitute an FV variable as the FEM potential.

`DDEnergyEq` creates absent FEM `log_e_energy`, but only with explicit
strictly positive finite `initial_molar_energy_density_eV` [eV mol/m^3].
The generated ConstantIC stores its logarithm, not `log(n_e)` and not a
default zero log state. Existing FEM energy variables and ICs remain under
Native ownership; specifying a second initial value fails.

```ini
[Physics]
  [Plasmas]
    files = plasma_auto_constant.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          # Format: species_name initial_number_density ... [1/m^3]
          fem_species = 'e 1e16'
          fem_potential = potential
        []
        [Energy]
          fem_species = e
          initial_molar_energy_density_eV = 4.98161720152154e-8
        []
      []
    []
    [Poisson]
      fem_potential = potential
      initial_potential_V = 0
    []
  []
[]
```

The example value is synthetic (1e16 particles/m^3 at 3 eV mean energy,
converted to mol eV/m^3); it is not a validated S6 parameter. The
Continuity `fem_potential` consumes a variable and **does not** create it;
`[Poisson]` owns the potential only when explicitly activated. Original
S6 archives and separate MultiApp ownership must not be changed.

Native P1 C++ compile, P2 positive/negative check-input, and scientific
equivalence are separate gates; this revision does not authorize P3.
