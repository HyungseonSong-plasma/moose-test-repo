# DriftDiffusion Continuity creates DDTransportMaterial for JSON species coefficients.
# Chemistry applies the minus sign to positive energy_loss_eV and native
# delta_epsilon_EI02/EI17 Functors. No extra manually declared Material block.
# Issue #402 S6-417 Chemistry cutover overlay; use ONLY with the staged S6
# native layers after the listed legacy electron-particle and energy Kernels
# have been removed in scratch. See chemistry/README.md; not a standalone deck.
# This overlay replaces (not supplements) migrated_continuity.i.
[Physics]
  [Plasmas]
    files = 'unified_s6_417.json'
    pressure = 1.333223684
    temperature = 300
    state_model = ideal_gas
    [Transport]
      [Chemistry]
        block = plasma
      []
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fem_species = 'e'
          fvm_species = 'O2p Om Op'
          fem_potential = potential
        []
        [Energy]
          block = plasma
          fem_species = 'e'
          fem_potential = potential
          initial_molar_energy_density_eV = 6.6421562686953756e-09
        []
      []
    []
  []
[]
