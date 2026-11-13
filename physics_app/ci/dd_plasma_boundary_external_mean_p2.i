# Alternate P2 migration: external mean-energy owner, JSON wall catalogue.
[Mesh]
  type = GeneratedMesh
  dim = 2
  nx = 2
  ny = 2
[]
[Problem]
  solve = false
  kernel_coverage_check = false
[]
[Variables]
  [log_ne]
    type = MooseVariable
  []
  [log_energy]
    type = MooseVariable
  []
  [potential]
    type = MooseVariable
  []
[]
[Physics]
  [Plasmas]
    files = dd_plasma_boundary_json_p2.json
    [Transport]
      [DriftDiffusion]
        plasma_boundary = json
        plasma_boundary_mean_energy_owner = external
        plasma_boundary_mean_energy = preexisting_mean_en
      []
    []
  []
[]
[FunctorMaterials]
  [electron_state]
    type = ADGenericFunctorMaterial
    prop_names = 'n_e_physical preexisting_mean_en'
    prop_values = '1e15 4.0'
  []
[]
[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
