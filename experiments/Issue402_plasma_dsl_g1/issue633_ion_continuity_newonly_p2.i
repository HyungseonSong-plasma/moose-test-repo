# Issue #633: minimal synthetic, Native-ion-free 3-species FV continuity P2.
# No Poisson, energy, wall/BC, or S6 numerical parity claim is made.
# The potential is an externally declared static FEM probe, NOT Poisson.
# Only JSON + selected Physics continuity generate the 3 x 4 FV kernels.
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
    initial_condition = 0
  []
[]
[FunctorMaterials]
  [synthetic_progress_and_carrier]
    type = ADGenericFunctorMaterial
    prop_names = 'R_EI415 R_EI401 R_EI417 carrier_one'
    prop_values = '1 1 1 1'
  []
[]
[Physics]
  [Plasmas]
    files = issue633_ion_continuity_newonly_p2.json
    [Transport]
      [Chemistry]
      []
      [DriftDiffusion]
        [Continuity]
          fvm_species = 'O2p Om Op'
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
