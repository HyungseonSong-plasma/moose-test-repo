# Issue402 JSON plasma boundary P2 construction fixture.
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
  [log_ne]
    type = MooseVariable
  []
  [log_energy]
    type = MooseVariable
  []
  [potential]
    type = MooseVariable
  []
[]
[Physics]
  [Plasmas]
    files = dd_plasma_boundary_json_p2.json
    [Transport]
      [DriftDiffusion]
        plasma_boundary = json
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
[]
[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
