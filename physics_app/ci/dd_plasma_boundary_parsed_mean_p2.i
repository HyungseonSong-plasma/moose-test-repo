# Optional ADParsedFunctorMaterial construction feasibility: NOT numerical parity.
# GeneratedMesh sideset mapping: left=wafer, bottom=cover, right=inlet, top=outlet.
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
  [log_e]
    type = MooseVariable
  []
  [log_e_energy]
    type = MooseVariable
  []
  [potential]
    type = MooseVariable
  []
[]
[Physics]
  [Plasmas]
    files = dd_plasma_boundary_json_p2.json
  []
[]
[FunctorMaterials]
  [physical_electron_density]
    type = ADGenericFunctorMaterial
    prop_names = n_e_physical
    prop_values = 1e15
  []
  [mean_energy_bridge]
    type = ADParsedFunctorMaterial
    property_name = e_energy_eV
    functor_names = 'log_e_energy log_e'
    functor_symbols = 'ue un'
    expression = 'exp(ue-un)'
  []
  [electron_wall_flux]
    type = ESWallFluxMaterial
    electron_density = n_e_physical
    mean_energy = e_energy_eV
    potential = potential
    use_element_gradient_for_potential = true
  []
[]
[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
