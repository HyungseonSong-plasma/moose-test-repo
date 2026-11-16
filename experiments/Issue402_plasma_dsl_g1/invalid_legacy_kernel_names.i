# Negative input: obsolete explicit FEM kernel names must be rejected by
# CURRENT JSON-generated Continuity. Overlay only the active standalone
# valid_generated_transport_json_p2.i, not old external-variable baseline.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_kernel_names = 'ne_transport'
        []
      []
    []
  []
[]
