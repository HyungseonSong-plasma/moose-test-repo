# Synthetic P2 only: demonstrate missing log_e, log_e_energy, and potential.
# Do not use these example initial values as physical S6 data.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]
[Problem]
  solve = false
  kernel_coverage_check = false
[]
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
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
