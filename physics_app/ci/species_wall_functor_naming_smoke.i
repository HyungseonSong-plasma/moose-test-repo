# Issue #402 species-first public Functor interface; P2 --check-input ONLY.
# No solver execution/P3 and no physical parity claim.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]
[Problem]
  solve = false
  kernel_coverage_check = false
[]
[Variables]
  [log_O2p]
    type = MooseVariableFVReal
  []
  [log_Op]
    type = MooseVariableFVReal
  []
  [log_Om]
    type = MooseVariableFVReal
  []
  [log_e]
    type = MooseVariableFVReal
  []
[]
[FunctorMaterials]
  [controlled_inputs]
    type = ADGenericFunctorMaterial
    prop_names = 'rho e_number_density w_O2p w_Om w_Op potential T_g mean_en_solved'
    prop_values = '1 1e15 1e-6 1e-6 1e-6 0 300 4'
  []
  [charged_species_density]
    type = PhysicsPlasmaChargeDensityMaterial
    density = rho
    electron_density = e_number_density
    ion_ids = 'O2p Om Op'
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    ion_molar_masses = '0.032 0.016 0.016'
    ion_charges = '1 -1 1'
    canonical_species_names = true
  []
  [O2p_transport]
    type = DDMaterial
    species_id = O2p
    model = constant
    mobility = 0.002
    diffusivity = 0.003
  []
  [Op_transport]
    type = DDMaterial
    species_id = Op
    model = constant
    mobility = 0.004
    diffusivity = 0.005
  []
  [Om_transport]
    type = DDMaterial
    species_id = Om
    model = constant
    mobility = 0.002
    diffusivity = 0.003
  []
  [O2p_wall]
    type = PhysicsIonWallFluxMaterial
    species_id = O2p
    ion_number_density = O2p_number_density
    potential = potential
    mobility = O2p_mobility
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.032
    sticking = 1
  []
  [Op_wall]
    type = PhysicsIonWallFluxMaterial
    species_id = Op
    ion_number_density = Op_number_density
    potential = potential
    mobility = Op_mobility
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.016
    sticking = 1
  []
  [Om_wall]
    type = PhysicsIonWallFluxMaterial
    species_id = Om
    ion_number_density = Om_number_density
    potential = potential
    mobility = Om_mobility
    gas_temperature = T_g
    charge_number = -1
    molar_mass = 0.016
    sticking = 1
  []
  [electron_wall]
    type = PhysicsElectronWallFluxMaterial
    species_id = e
    electron_density = e_number_density
    mean_energy = mean_en_solved
    sticking = 1
  []
[]
[FVBCs]
  [O2p_wall]
    type = FVFunctorNeumannBC
    variable = log_O2p
    functor = O2p_wall_number_flux
    factor = -1.6605390671738466e-24
    boundary = right
  []
  [Op_wall]
    type = FVFunctorNeumannBC
    variable = log_Op
    functor = Op_wall_number_flux
    factor = -1.6605390671738466e-24
    boundary = right
  []
  [Om_wall]
    type = FVFunctorNeumannBC
    variable = log_Om
    functor = Om_wall_number_flux
    factor = -1.6605390671738466e-24
    boundary = right
  []
  [e_wall]
    type = FVFunctorNeumannBC
    variable = log_e
    functor = e_wall_number_flux
    factor = -1.6605390671738466e-24
    boundary = right
  []
[]
[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
