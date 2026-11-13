# Exact legacy .i [BCs] control; JSON has no boundary catalogue.
# Issue402 verbatim BC JSON migration fixture; no .i selector.
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
    files = json_surface_rate_p2.json
  []
[]
[FunctorMaterials]
  [physical_electron_density]
    type = ADGenericFunctorMaterial
    prop_names = n_e_physical
    prop_values = 1e15
  []
  [mean_energy_bridge]
    type = PhysicsElectronMeanEnergyMaterial
    state_form = log_molar_eV
    electron_energy_density = log_energy
    electron_density = log_ne
    mean_energy_output = e_mean_energy
  []
  [electron_wall_flux]
    type = PhysicsElectronAdjacentSheathWallFluxMaterial
    electron_density = n_e_physical
    mean_energy = e_mean_energy
    potential = potential
    use_element_gradient_for_potential = true
  []
[]
[BCs]
  [electron_wafer]
    type = FEMElectronSheathBC
    variable = log_ne
    boundary = left
    wall_number_flux = electron_wall_number_flux
  []
  [electron_energy_wafer]
    type = FEMElectronEnergySheathBC
    variable = log_energy
    boundary = left
    wall_number_flux = electron_wall_number_flux
    mean_energy = e_mean_energy
  []
  [electron_cover]
    type = FEMElectronSheathBC
    variable = log_ne
    boundary = bottom
    wall_number_flux = electron_wall_number_flux
  []
  [electron_energy_cover]
    type = FEMElectronEnergySheathBC
    variable = log_energy
    boundary = bottom
    wall_number_flux = electron_wall_number_flux
    mean_energy = e_mean_energy
  []
[]
[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
