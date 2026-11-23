# Issue #633 NEW-ONLY target Continuity overlay; not a standalone S6 input.
# Stage in a disposable 11-layer Scratch directory with the integrated JSON
# and existing external electron/rate/neutral/RF owners. This is NOT P2 PASS.
# Keep historical Hybrid templates and original Native inputs unchanged.
[Physics]
  [Plasmas]
    files = 'chemistry/unified_s6_941_newonly.json'
    pressure = 1.333223684
    temperature = 300
    state_model = ideal_gas
    # Shared FEM-potential gradient evaluation for every C2 FV ion wall.
    wall_gradient = adjacent_element
    [Transport]
      [Chemistry]
        block = plasma
      []
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fem_species = e
          fvm_species = 'O2p Om Op'
          fem_potential = potential
          # Optional [V/m]: omit or set 0 for exact hard max(x,0).
          # Historical S6 sets 0.001 explicitly to retain its prior gate.
          migration_smoothing_width = 0.001
        []
        [Energy]
          block = plasma
          fem_species = e
          fem_potential = potential
          transport_coefficient = fluid
        []
      []
    []
  []
[]
