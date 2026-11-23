# Synthetic combined Physics/JSON ownership check; P2 --check-input only.
# DO NOT merge with baseline.i, which owns its own Variables/Kernels/BCs.
# This file validates the modern source of electron/ion ICs, Energy, Poisson,
# Chemistry and independent RF real/imag fields, not numerical/S6 parity.
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
  [E_real]
    family = LAGRANGE
    order = FIRST
  []
  [E_imag]
    family = LAGRANGE
    order = FIRST
  []
[]
[Materials]
  [rf_coefficients]
    type = GenericConstantMaterial
    prop_names = 'neg_a b'
    prop_values = '-1 0.2'
  []
[]
[Physics]
  [Plasmas]
    files = plasma_all_physics_json_p2.json
    [Transport]
      [Chemistry]
      []
      [DriftDiffusion]
        [Continuity]
          fem_species = e
          fvm_species = O2p
          # P2-only binding/JSON coefficient fixture, not a full FV equation.
          dont_create_kernels = true
          fem_potential = potential
        []
        [Energy]
          fem_species = e
          fem_potential = potential
          initial_molar_energy_density_eV = 4.98161720152154e-8
        []
      []
    []
    [Poisson]
      fem_potential = potential
      initial_potential_V = 0
    []
    [Maxwell]
      field_real = E_real
      field_imag = E_imag
      frequency_hz = 13560000
      reaction_material = neg_a
      coupling_material = b
      imaginary_source = 1
      ground_boundaries = 'left right'
    []
  []
[]
[Executioner]
  type = Transient
  dt = 1e-6
  num_steps = 1
[]
