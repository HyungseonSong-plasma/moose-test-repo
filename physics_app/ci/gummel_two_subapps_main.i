[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]

[Problem]
  solve = false
  kernel_coverage_check = false
[]

[GummelIteration]
  [electron_poisson]
    electron_multiapp = electron
    electron_input_file = gummel_two_subapps_electron.i

    poisson_multiapp = poisson
    poisson_input_file = gummel_two_subapps_poisson.i

    # Core sibling sharing is automatic:
    #   electron.n_e -> poisson.n_e
    #   poisson.phi  -> electron.phi
    electron_density_variable = n_e
    poisson_electron_density_variable = n_e
    poisson_potential_variable = phi
    electron_potential_variable = phi

    # Optional additional electron state needed by Poisson closures.
    electron_to_poisson_source_variables = 'mean_en'
    electron_to_poisson_variables = 'mean_en'

    poisson_transformed_variables = 'phi'
    relaxation_factor = 0.45
    no_restore = true
    manage_convergence = false
  []
[]

[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
