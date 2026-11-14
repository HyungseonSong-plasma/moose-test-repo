# Issue #402 synthetic P2 test: FEM + 3 FVM species use JSON-owned DDTransportMaterial.
# Species/initial number density [1/m^3] pairs are declared only in Continuity.
# The rates, electron lookup table and ion constants below are NOT physical S6 data.
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
  []
[]
[FunctorMaterials]
  # Thermodynamic test Functors; not coefficient providers.
  [synthetic_dd_state]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en_solved p T_g'
    prop_values = '3 100 300'
  []
[]
[Physics]
  [Plasmas]
    files = invalid_json_dd_missing_om_p2.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          # Format: species_name initial_number_density ...
          fem_species = 'e 1e16'
          fvm_species = 'O2p 1e16 Om 1e14 Op 1e15'
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
