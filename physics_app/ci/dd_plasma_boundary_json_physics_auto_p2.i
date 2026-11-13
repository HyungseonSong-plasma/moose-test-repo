# P2 input-construction only: JSON + Physics auto-generate log_e/log_e_energy and BCs.
# No full energy drift/diffusion/time equation or physics time integration.
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
  [potential]
    type = MooseVariable
  []
[]
[Physics]
  [Plasmas]
    files = dd_plasma_boundary_json_p2.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e 1e15'
        []
        [Energy]
          fem_species = e
          initial_molar_energy_density_eV = 8.3e-9
        []
      []
    []
  []
[]
[FunctorMaterials]
  [physical_electron_density]
    type = ADGenericFunctorMaterial
    prop_names = n_e_physical
    prop_values = 1e15
  []
  [mean_energy_bridge]
    type = ElectronEnergyMaterial
    state_form = log_molar_eV
    electron_energy_density = log_e_energy
    electron_density = log_e
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
