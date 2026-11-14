# Issue402 bounded native P3 smoke: real FEM electron continuity + energy
# evolution assembled solely from JSON species, Physics Actions and existing
# kernels/materials/BCs. This is NOT S6/RF/chemistry scientific parity.
# The driver runs this identical .i twice: JSON sheath on vs. boundaries absent.
# No new C++ physics is implemented.
[Mesh]
  type = GeneratedMesh
  dim = 2
  nx = 4
  ny = 4
  xmin = 0
  xmax = 0.01
  ymin = 0
  ymax = 0.01
[]
[Variables]
  [potential]
    family = LAGRANGE
    order = FIRST
  []
[]
[ICs]
  [potential_initial]
    type = ConstantIC
    variable = potential
    value = 0
  []
[]
[Kernels]
  [potential_laplace]
    type = Diffusion
    variable = potential
  []
[]
[BCs]
  [potential_ground]
    type = DirichletBC
    variable = potential
    boundary = 'left right top bottom'
    value = 0
  []
[]
[Physics]
  [Plasmas]
    files = dd_plasma_boundary_json_p2.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = e
          fem_potential = potential
        []
        [Energy]
          fem_species = e
          fem_potential = potential
          initial_molar_energy_density_eV = 8.3e-9
        []
      []
    []
  []
[]
[Postprocessors]
  [avg_log_e]
    type = ElementAverageValue
    variable = log_e
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [avg_log_e_energy]
    type = ElementAverageValue
    variable = log_e_energy
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [avg_e_energy_eV]
    type = ElementAverageFunctorPostprocessor
    functor = e_energy_eV
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
[Executioner]
  type = Transient
  dt = 1e-10
  num_steps = 2
  solve_type = NEWTON
  nl_rel_tol = 1e-8
  nl_abs_tol = 1e-12
  nl_max_its = 20
[]
[Outputs]
  file_base = plasma
  exodus = true
  csv = true
[]
