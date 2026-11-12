# Negative P2 control: native and ContinuityEq must not both own electron time.
# Layer after baseline.i and valid_generated_transport_options.i.
[Kernels]
  [native_duplicate_e_time]
    type = PhysicsFEMLogMolarTimeDerivative
    variable = log_e
  []
[]
