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
# log_O2p and FVConstantIC are generated from species JSON.
[FunctorMaterials]
  [synthetic_ion_coefficients]
    type = ADGenericFunctorMaterial
    prop_names = 'upstream_ion_mobility upstream_ion_diffusivity'
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
