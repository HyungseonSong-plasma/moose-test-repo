# Synthetic check-input only. Existing AD functors supply ion coefficients.
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
  [log_O2p]
    type = MooseVariableFVReal
  []
[]
[FunctorMaterials]
  [synthetic_ion_coefficients]
    type = ADGenericFunctorMaterial
    prop_names = 'ion_mobility ion_diffusion'
    prop_values = '0.2 0.05'
  []
[]
[Physics]
  [Plasmas]
    files = plasma_auto_functor.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fvm_species = O2p
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
