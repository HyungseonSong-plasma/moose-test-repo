# P2 only: JSON + Physics generate electron continuity/energy states, conservative
# time, drift-diffusion, Joule, mean-energy and sheath flux providers, plus BCs.
# No physical time integration or scientific parity assertion.
# S6-941 P2 synthetic sidesets: left=electrode/metal/right, bottom=cover,
# right=wafer, top=focus_ring. No private EI rates or physical P3 solve.
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
  [potential]
    type = MooseVariable
  []
  [log_Op]
    type = MooseVariableFVReal
  []
[]
[Physics]
  [Plasmas]
    files = s6_941_electron_fem_p2.json
    pressure = 1.333223684
    temperature = 300
    state_model = ideal_gas
    [Transport]
      [Chemistry]
      []
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
[FunctorMaterials]
  [synthetic_live_composition]
    type = ADGenericFunctorMaterial
    prop_names = 'w_O2 w_O w_O2p w_Om w_Op w_O2a'
    prop_values = '1 0 0 0 0 0'
  []
[]
[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
