# Negative JSON charge-ownership contract. The old missing-FVM-charge
# positional-vector layout is retired: charges come solely from species
# entries in Chemistry JSON. A forbidden fem_charge_numbers must fail closed.
# Overlay on valid_generated_transport_json_p2.i, not the external-variable
# baseline that masks invalid options with missing JSON initial densities.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_charge_numbers = '-1'
        []
      []
    []
  []
[]
