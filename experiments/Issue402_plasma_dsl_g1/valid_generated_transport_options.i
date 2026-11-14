# P2 JSON-owned FEM e construction; never compose with baseline.i's
# external log_e Variable, Diffusion kernels or initial condition.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 4
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
          fem_species = 'e'
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
