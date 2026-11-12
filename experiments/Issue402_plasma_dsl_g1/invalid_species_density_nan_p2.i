# Issue #402 density-paired species syntax, Native P2 only.
# Format: species_name initial_number_density ...
# initial_number_density in 1/m^3, must be finite and >0.
# Transport coefficients are JSON-owned; physics-rate values here are synthetic.
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
  [potential]
    family = LAGRANGE
    order = FIRST
  []
[]
[Physics]
  [Plasmas]
    files = plasma_auto_constant.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e nan'
          fvm_species = 'O2p 1e16 Om 1e14 Op 1e15'
          fem_potential = potential
        []
      []
    []
  []
[]
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
