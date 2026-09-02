# ==============================================================================
# R14 EVR1-B — independent D_k,m oracle parity + charged ne sensitivity
#
# A: ne = 1e16 m^-3
# B: ne = 1e18 m^-3
#
# Same T, p, Te and mass fractions in both material instances.
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
    prop_names = 'T_g p_abs T_e n_e_A n_e_B w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    prop_values = '600 13.332 20000 1e16 1e18 0.70 0.05 0.01 0.10 0.01 0.01 0.12'
  []

  [transport_A]
    type = QPXThermalDiffusionMaterial
    temperature = T_g
    pressure = p_abs
    electron_temperature = T_e
    electron_number_density = n_e_A
    transport_data_file = transport_data.txt
    species = 'O2 O2s O2p O Om Op Os'
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    D_mix_names = 'Dmix_A_O2 Dmix_A_O2s Dmix_A_O2p Dmix_A_O Dmix_A_Om Dmix_A_Op Dmix_A_Os'
    D_T_names = 'DT_A_O2 DT_A_O2s DT_A_O2p DT_A_O DT_A_Om DT_A_Op DT_A_Os'
    kT_names = 'kT_A_O2 kT_A_O2s kT_A_O2p kT_A_O kT_A_Om kT_A_Op kT_A_Os'
  []

  [transport_B]
    type = QPXThermalDiffusionMaterial
    temperature = T_g
    pressure = p_abs
    electron_temperature = T_e
    electron_number_density = n_e_B
    transport_data_file = transport_data.txt
    species = 'O2 O2s O2p O Om Op Os'
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    D_mix_names = 'Dmix_B_O2 Dmix_B_O2s Dmix_B_O2p Dmix_B_O Dmix_B_Om Dmix_B_Op Dmix_B_Os'
    D_T_names = 'DT_B_O2 DT_B_O2s DT_B_O2p DT_B_O DT_B_Om DT_B_Op DT_B_Os'
    kT_names = 'kT_B_O2 kT_B_O2s kT_B_O2p kT_B_O kT_B_Om kT_B_Op kT_B_Os'
  []
[]

[Postprocessors]
  [Dmix_A_O2]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_O2
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_A_O2s]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_O2s
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_A_O2p]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_O2p
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_A_O]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_O
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_A_Om]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_Om
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_A_Op]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_Op
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_A_Os]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_A_Os
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_B_O2]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_O2
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_B_O2s]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_O2s
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_B_O2p]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_O2p
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_B_O]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_O
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_B_Om]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_Om
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_B_Op]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_Op
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Dmix_B_Os]
    type = ElementAverageFunctorPostprocessor
    functor = Dmix_B_Os
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
