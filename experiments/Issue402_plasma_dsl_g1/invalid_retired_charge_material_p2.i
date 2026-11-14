# Native P2 negative control: old charge-transport Material is retired.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]
[Problem]
  kernel_coverage_check = false
  solve = false
[]
[FunctorMaterials]
  [obsolete_charge]
    type = PlasmaChargeTransportMaterial
  []
[]
[Executioner]
  type = Steady
[]
