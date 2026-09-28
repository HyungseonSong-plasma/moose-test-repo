[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]

[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [phi]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

[AuxVariables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1.0e16
  []
  [mean_en]
    type = MooseVariableFVReal
    initial_condition = 5.73276e16
  []
  [rho_from_heavy]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [w_ion_from_heavy]
    type = MooseVariableFVReal
    initial_condition = 1.0e-6
  []
[]

[PlasmaClosures]
  [charge]
    role = electrostatic_charge
    mixture_density = rho_from_heavy
    electron_number_density = n_e
    charged_species_ids = 'ion'
    charged_species_mass_fractions = 'w_ion_from_heavy'
    charged_species_molar_masses = '0.032'
    charged_species_charge_numbers = '1'
  []
[]

[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
