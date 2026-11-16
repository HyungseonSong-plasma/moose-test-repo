# Issue402 synthetic option-first FEM transport P2, modern JSON owns species IC.
# Standalone: legacy baseline.i externally declares log_e/BCs and cannot be
# combined with generated e_time/e_transport without duplicate ownership.
# No physical rates, timesteps, or S6 scientific equivalence are asserted.
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
    files = plasma_species_initial_p2.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = e
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
