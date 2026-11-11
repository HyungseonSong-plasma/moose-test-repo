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
# Standalone P2-only residuals satisfy MOOSE kernel-coverage integrity.
# ContinuityEq remains a pure variable-binding check in this fixture.
[Kernels]
  [electron_diffusion_probe]
    type = Diffusion
    variable = log_e
  []
[]
[FVKernels]
  [o2p_diffusion_probe]
    type = FVDiffusion
    variable = log_O2p
    coeff = 1
  []
  [om_diffusion_probe]
    type = FVDiffusion
    variable = log_Om
    coeff = 1
  []
  [op_diffusion_probe]
    type = FVDiffusion
    variable = log_Op
    coeff = 1
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
