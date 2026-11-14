# Issue #402 synthetic P2 test: FEM + 3 FVM species use JSON-owned DDTransportMaterial.
# Continuity selects species IDs; JSON species owns initial number density [1/m^3].
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
    prop_names = 'e_energy_eV p T_g'
    prop_values = '3 100 300'
  []
[]
[Physics]
  [Plasmas]
    files = invalid_json_dd_bad_lookup_p2.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = e
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
