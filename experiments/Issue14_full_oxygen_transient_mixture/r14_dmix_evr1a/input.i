# ==============================================================================
# R14 EVR1-A — seven-species QPXThermalDiffusionMaterial production runtime probe
#
# Scope:
#   - production qpx-opt
#   - actual R14 D_mix source candidate
#   - actual local seven-species transport database resolved by prepare.py
#   - O2 O2s O2p O Om Op Os
#   - runtime exposure of D_mix_<species>, D_T_<species>, kT_<species>
#
# Deliberately NOT claimed here:
#   - full Q-1 transient heavy-mixture continuity
#   - mixture Mn/rho/drho_dt evolution
#   - thermal-gradient flux closure
#   - D_mix independent runtime oracle parity
# Those belong to the next EVR1 tranches after this production material probe.
# ==============================================================================

[Mesh]
  [mesh]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 2
    xmin = 0
    xmax = 1
  []
[]

[Variables]
  [dummy]
    initial_condition = 0
  []
[]

[Kernels]
  [dummy_reaction]
    type = Reaction
    variable = dummy
  []
[]

[FunctorMaterials]
  [state]
    type = ADGenericFunctorMaterial
    prop_names = 'T_g p_abs T_e n_e w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    prop_values = '600 13.332 20000 1e16 0.70 0.05 0.01 0.10 0.01 0.01 0.12'
  []

  [thermal_transport]
    type = QPXThermalDiffusionMaterial
    temperature = T_g
    pressure = p_abs
    electron_temperature = T_e
    electron_number_density = n_e
    transport_data_file = transport_data.txt
    species = 'O2 O2s O2p O Om Op Os'
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
  []
[]

[Postprocessors]
  [D_mix_O2]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_O2
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [D_mix_O2s]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_O2s
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [D_mix_O2p]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_O2p
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [D_mix_O]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_O
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [D_mix_Om]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_Om
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [D_mix_Op]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_Op
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [D_mix_Os]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_Os
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [D_T_O2]
    type = ElementAverageFunctorPostprocessor
    functor = D_T_O2
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [D_T_O2s]
    type = ElementAverageFunctorPostprocessor
    functor = D_T_O2s
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [D_T_O2p]
    type = ElementAverageFunctorPostprocessor
    functor = D_T_O2p
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [D_T_O]
    type = ElementAverageFunctorPostprocessor
    functor = D_T_O
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [D_T_Om]
    type = ElementAverageFunctorPostprocessor
    functor = D_T_Om
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [D_T_Op]
    type = ElementAverageFunctorPostprocessor
    functor = D_T_Op
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [D_T_Os]
    type = ElementAverageFunctorPostprocessor
    functor = D_T_Os
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [kT_O2]
    type = ElementAverageFunctorPostprocessor
    functor = kT_O2
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [kT_O2s]
    type = ElementAverageFunctorPostprocessor
    functor = kT_O2s
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [kT_O2p]
    type = ElementAverageFunctorPostprocessor
    functor = kT_O2p
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [kT_O]
    type = ElementAverageFunctorPostprocessor
    functor = kT_O
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [kT_Om]
    type = ElementAverageFunctorPostprocessor
    functor = kT_Om
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [kT_Op]
    type = ElementAverageFunctorPostprocessor
    functor = kT_Op
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [kT_Os]
    type = ElementAverageFunctorPostprocessor
    functor = kT_Os
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_abs_tol = 1e-12
  nl_rel_tol = 1e-12
  nl_max_its = 10
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
