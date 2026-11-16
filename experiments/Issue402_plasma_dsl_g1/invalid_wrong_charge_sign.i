# Negative option contract: charge signs are JSON-owned and obsolete
# fem_charge_numbers/fvm_charge_numbers must be rejected, not interpreted.
# Overlay modern valid_generated_transport_json_p2.i with JSON electron IC;
# old baseline and species_only.json mask these keys via missing density.
[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_charge_numbers = '1'
          fvm_charge_numbers = '1'
        []
      []
    []
  []
[]
