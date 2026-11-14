# P2 negative-control infrastructure only. Deliberately has no plasma
# solver variables, chemical sources, or Physics equation owners.
# This supplies a valid MOOSE mesh/execution environment so malformed
# JSON/DSL inputs are rejected for their targeted contract violation.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
[]
[Problem]
  solve = false
  kernel_coverage_check = false
[]
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
