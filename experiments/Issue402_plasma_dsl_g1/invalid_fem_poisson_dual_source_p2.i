# Issue402 P2: FEM Poisson consumes the same AD charge Functor used in FV.
# Synthetic values; --check-input only. Not an S6 simulation.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]
[Problem]
  kernel_coverage_check = false
  solve = false
[]
[Physics]
  [Plasmas]
    files = plasma_noop_control.json
    [Poisson]
      fem_potential = potential
      charge_source_functor = poisson_charge_source
      charge_source_material = legacy_charge_property
      ground_boundaries = 'left right'
    []
  []
[]
[FunctorMaterials]
  [state]
    type = ADGenericFunctorMaterial
    prop_names = 'rho ne w_O2p'
    prop_values = '1 1e16 1e-5'
  []
  [charge]
    type = PhysicsPlasmaChargeDensityMaterial
    density = rho
    electron_density = ne
    ion_ids = 'O2p'
    ion_mass_fractions = 'w_O2p'
    ion_molar_masses = '0.032'
    ion_charges = '1'
  []
[]
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
