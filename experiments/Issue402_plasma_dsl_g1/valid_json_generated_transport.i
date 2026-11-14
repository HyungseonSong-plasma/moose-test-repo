# JSON-owned DD lookup/constant + NV collision database wiring (P2 only).
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
  [log_e]
    family = LAGRANGE
    order = FIRST
  []
  [log_O2p]
    type = MooseVariableFVReal
  []
  [potential]
    family = LAGRANGE
    order = FIRST
  []
[]
[FunctorMaterials]
  # These are state/thermodynamic test Functors, not transport coefficient providers.
  [test_state]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en_solved p T_g Y_A Y_B'
    prop_values = '3 100 300 0.5 0.5'
  []
[]
[Physics]
  [Plasmas]
    files = 'plasma_auto_lookup.json plasma_auto_navier_stokes.json'
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = e
          fvm_species = O2p
          fem_potential = potential
        []
      []
      [NavierStokes]
      []
    []
  []
[]
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
