# DriftDiffusion Continuity creates DDTransportMaterial for JSON species coefficients.
# Chemistry applies the minus sign to positive energy_loss_eV and native
# delta_epsilon_EI02/EI17 Functors. No extra manually declared Material block.
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
