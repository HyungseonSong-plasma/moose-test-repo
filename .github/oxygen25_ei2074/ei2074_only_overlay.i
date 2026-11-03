# Research-only EI-2074 overlay: one reaction added to Legacy8 + H05 + EI417 + EI2072
# e + O2(a1Delta) -> O+ + O(3P) + 2e
# Net +1 free electron; existing HPEM lookup energy sink 16.023 eV/event
# SCIENCE_HOLD. Do not make independent O2(X), O2+, or O- sources.
[FunctorMaterials]
  [ei2074_target]
    type = ADParsedFunctorMaterial
    property_name = c_O2a_EI2074
    functor_names = 'rho_neutral w_O2s'
    functor_symbols = 'rho w'
    expression = 'rho*w/0.032'
    block = plasma
  []
  [ei2074_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = 'private_rates/EI-2074_O2_a1Delta.txt'
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O2a_EI2074
    reaction_progress = R_EI2074
    block = plasma
  []
  [ei2074_electron]
    type = ADParsedFunctorMaterial
    property_name = S_e_molar_EI2074
    functor_names = 'R_EI2074'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [ei2074_op_molar]
    type = ADParsedFunctorMaterial
    property_name = S_Op_molar_EI2074
    functor_names = 'R_EI2074'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [ei2074_o2a_mass]
    type = ADParsedFunctorMaterial
    property_name = S_O2a_mass_EI2074
    functor_names = 'R_EI2074'
    functor_symbols = 'R'
    expression = '-0.032*R'
    block = plasma
  []
  [ei2074_o_mass]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_EI2074
    functor_names = 'R_EI2074'
    functor_symbols = 'R'
    expression = '0.016*R'
    block = plasma
  []
  [ei2074_op_mass]
    type = ADParsedFunctorMaterial
    property_name = S_Op_mass_EI2074
    functor_names = 'R_EI2074'
    functor_symbols = 'R'
    expression = '0.016*R'
    block = plasma
  []
  [ei2074_neutral_mass]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_EI2074
    functor_names = 'R_EI2074'
    functor_symbols = 'R'
    expression = '-0.016*R'
    block = plasma
  []
  [ei2074_energy]
    type = ADParsedFunctorMaterial
    property_name = S_energy_EI2074
    functor_names = 'R_EI2074'
    functor_symbols = 'R'
    expression = '-16.023*R'
    block = plasma
  []
  [ei2074_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_EI2074
    functor_names = 'S_O2a_mass_EI2074 S_O_mass_EI2074 S_Op_mass_EI2074'
    functor_symbols = 'a b c'
    expression = 'a+b+c'
    block = plasma
  []
  [ei2074_neutral_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_closure_EI2074
    functor_names = 'S_O2a_mass_EI2074 S_O_mass_EI2074 S_neutral_mass_EI2074'
    functor_symbols = 'a b c'
    expression = 'a+b-c'
    block = plasma
  []
  [ei2074_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_closure_EI2074
    functor_names = 'S_e_molar_EI2074 S_Op_molar_EI2074'
    functor_symbols = 'el ion'
    expression = 'ion-el'
    block = plasma
  []
[]
[Kernels]
  [ei2074_electron_source]
    type = FunctorKernel
    variable = log_ne
    functor = S_e_molar_EI2074
    functor_on_rhs = true
    block = plasma
  []
  [ei2074_electron_energy_sink]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_EI2074
    functor_on_rhs = true
    block = plasma
  []
[]
[FVKernels]
  [ei2074_o2a_sink]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O2s
    source = S_O2a_mass_EI2074
    block = plasma
  []
  [ei2074_o_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_EI2074
    block = plasma
  []
  [ei2074_op_source]
    type = FVCoupledForce
    variable = log_nop
    v = S_Op_molar_EI2074
    coef = 1.0
    block = plasma
  []
  [ei2074_neutral_mass_sink]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_EI2074
    coef = 1.0
    block = plasma
  []
[]
[Postprocessors]
  [ei2074_rate_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_EI2074
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2074_electron_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_e_molar_EI2074
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2074_energy_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_energy_EI2074
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2074_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_EI2074
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2074_neutral_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_neutral_mass_closure_EI2074
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2074_charge_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_closure_EI2074
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
