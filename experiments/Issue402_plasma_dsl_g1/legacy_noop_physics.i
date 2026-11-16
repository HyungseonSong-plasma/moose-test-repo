# Legacy no-op numerical-parity overlay: intentionally reuses the
# pre-existing FEM log_e, FV log_O2p and RF imaginary solver variables
# from baseline.i. No JSON continuity/energy/Chemistry equation generator
# is enabled; Poisson and Maxwell validate external state without kernels.
# This is NOT an electron FEM equation-construction or S6 science test.
[Physics]
  [Plasmas]
    files = plasma_noop_control.json
    [Poisson]
      fem_potential = log_e
    []
    [Maxwell]
      field_real = log_e
      field_imag = u_rf_imag
      frequency_hz = 13560000
    []
  []
[]
