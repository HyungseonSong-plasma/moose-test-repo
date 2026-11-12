# Issue #402 S6-417 Chemistry cutover overlay; use ONLY with the staged S6
# native layers after the listed legacy electron-particle and energy Kernels
# have been removed in scratch. See chemistry/README.md; not a standalone deck.
# REVIEW-ONLY: e_transport.txt uses synthetic P2 smoke values, not validated Boltzmann transport.
# The original Native electron coefficient owner must be retired in scratch
# before activating this JSON to avoid duplicate Functor names.
# This OVERLAY is not a standalone full Native S6 .i file.
# This overlay replaces (not supplements) migrated_continuity.i.
[Physics]
  [Plasmas]
    files = 'chemistry/review_s6_417_full.json'
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
        []
      []
    []
  []
[]
[FunctorMaterials]
  # Native EI-02/EI-17 delta_epsilon_* give a POSITIVE loss magnitude;
  # the Chemistry JSON functor contract requires signed energy change.
  [ei02_signed_energy_change]
    type = ADParsedFunctorMaterial
    property_name = signed_delta_epsilon_EI02_eV
    functor_names = 'delta_epsilon_EI02_eV'
    functor_symbols = 'loss'
    expression = '-loss'
    block = plasma
  []
  [ei17_signed_energy_change]
    type = ADParsedFunctorMaterial
    property_name = signed_delta_epsilon_EI17_eV
    functor_names = 'delta_epsilon_EI17_eV'
    functor_symbols = 'loss'
    expression = '-loss'
    block = plasma
  []
[]
