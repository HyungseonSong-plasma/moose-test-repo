# Issue402 G1: additive metadata only for S6-417 or S6-941.
# Apply AFTER the existing ten S6 inputs. This action is validation-only
# and creates NO variables, FEM/FV equations, material, source, BC, or transfers.
# IMPORTANT: this is not a full [Physics]/[Plasmas] implementation.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          owner_mode = external
          block = plasma
          fem_species = 'e'
          fvm_species = 'O2p Om Op'
          variables = 'log_ne log_ni log_nm log_nop'
        []
      []
    []
  []
[]
