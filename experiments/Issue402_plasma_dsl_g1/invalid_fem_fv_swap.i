# Negative owner guard: baseline.i already declares log_O2p as FV and log_e
# as FEM. The current JSON-owned Continuity must reject the attempted swapped
# FEM=O2p/FVM=e generation BEFORE silently reusing either old solver variable.
# This is not the unreachable historical "wrong type" diagnostic: JSON now
# generates each correctly typed state and rejects preexisting owners first.
# The selected fixture JSON must contain ICs for both e and O2p, otherwise the
# test fails prematurely on missing e IC instead of the duplicate FV owner.
[Physics]
  [Plasmas]
    files = plasma_species_initial_p2.json
    [Transport]
      [Chemistry]
      []
      [DriftDiffusion]
        [Continuity]
          fem_species = 'O2p'
          fvm_species = 'e'
          fem_potential = u_rf_imag
        []
      []
    []
  []
[]
