# Fail-closed missing-species JSON source guard, not the retired external
# solver-variable lookup. The active e/O2p states have valid JSON IC metadata;
# synthetic species 'missing' has no record, so it must fail by exact name.
[Physics]
  [Plasmas]
    files = plasma_species_initial_p2.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'missing'
          fvm_species = 'O2p'
        []
      []
    []
  []
[]
