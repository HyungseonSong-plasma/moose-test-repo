# P2 only: prove automatic log_<species> binding for 4 generic states.
# No transport generation or time-dependent solver is requested.
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 8
[]
[Variables]
  [log_e]
    family = LAGRANGE
    order = FIRST
  []
  [log_O2p]
    type = MooseVariableFVReal
  []
  [log_Om]
    type = MooseVariableFVReal
  []
  [log_Op]
    type = MooseVariableFVReal
  []
[]
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e'
          fvm_species = 'O2p Om Op'
        []
      []
    []
  []
[]
[Executioner]
  type = Steady
[]
