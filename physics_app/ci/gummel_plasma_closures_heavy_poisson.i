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
  [rho_from_heavy]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [w_O2p_from_heavy]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
  []
  [w_Om_from_heavy]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
  []
  [w_Op_from_heavy]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
  []
[]

[PlasmaClosures]
  [charge]
    role = electrostatic_charge
    mixture_density = rho_from_heavy
    electron_number_density = n_e
    charged_species_ids = 'O2p Om Op'
    charged_species_mass_fractions = 'w_O2p_from_heavy w_Om_from_heavy w_Op_from_heavy'
    charged_species_molar_masses = '0.032 0.016 0.016'
    charged_species_charge_numbers = '1 -1 1'
  []
[]

[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
