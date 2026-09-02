# ==============================================================================
# R14 EVR1-C — production thermal-gradient activation / ON-OFF localization
#
# Observable probes:
#   probe_grad_on  : T(x)=500+200x+100x^2, thermal kernel ON
#   probe_grad_off : same T(x), thermal kernel OFF
#   probe_flat_on  : T=600 K, thermal kernel ON
#
# Each probe also has FVReaction so the prescribed thermal-flux divergence
# appears as a unique steady solution response.
# ==============================================================================

[Mesh]
  [mesh]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 40
    xmin = 0
    xmax = 1
  []
[]

[GlobalParams]
  two_term_boundary_expansion = true
[]

[Variables]
  [probe_grad_on]
    type = MooseVariableFVReal
    initial_condition = 0
  []
  [probe_grad_off]
    type = MooseVariableFVReal
    initial_condition = 0
  []
  [probe_flat_on]
    type = MooseVariableFVReal
    initial_condition = 0
  []
[]

[AuxVariables]
  [T_grad]
    type = MooseVariableFVReal
  []
  [T_flat]
    type = MooseVariableFVReal
  []
  [DT_grad_O_aux]
    type = MooseVariableFVReal
  []
  [DT_flat_O_aux]
    type = MooseVariableFVReal
  []
[]

[Functions]
  [T_grad_fn]
    type = ParsedFunction
    expression = '500.0 + 200.0*x + 100.0*x^2'
  []
  [T_flat_fn]
    type = ConstantFunction
    value = 600.0
  []
[]

[ICs]
  [T_grad_ic]
    type = FunctionIC
    variable = T_grad
    function = T_grad_fn
  []
  [T_flat_ic]
    type = FunctionIC
    variable = T_flat
    function = T_flat_fn
  []
[]

[AuxKernels]
  [DT_grad_O_copy]
    type = FunctorAux
    variable = DT_grad_O_aux
    functor = DT_grad_O
    execute_on = 'INITIAL'
  []
  [DT_flat_O_copy]
    type = FunctorAux
    variable = DT_flat_O_aux
    functor = DT_flat_O
    execute_on = 'INITIAL'
  []
[]

[FunctorMaterials]
  [state]
    type = ADGenericFunctorMaterial
    prop_names = 'p_abs T_e n_e w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    prop_values = '13.332 20000 1e16 0.70 0.05 0.01 0.10 0.01 0.01 0.12'
  []

  [thermal_grad]
    type = QPXThermalDiffusionMaterial
    temperature = T_grad
    pressure = p_abs
    electron_temperature = T_e
    electron_number_density = n_e
    transport_data_file = transport_data.txt
    species = 'O2 O2s O2p O Om Op Os'
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    D_mix_names = 'Dmix_grad_O2 Dmix_grad_O2s Dmix_grad_O2p Dmix_grad_O Dmix_grad_Om Dmix_grad_Op Dmix_grad_Os'
    D_T_names = 'DT_grad_O2 DT_grad_O2s DT_grad_O2p DT_grad_O DT_grad_Om DT_grad_Op DT_grad_Os'
    kT_names = 'kT_grad_O2 kT_grad_O2s kT_grad_O2p kT_grad_O kT_grad_Om kT_grad_Op kT_grad_Os'
  []

  [thermal_flat]
    type = QPXThermalDiffusionMaterial
    temperature = T_flat
    pressure = p_abs
    electron_temperature = T_e
    electron_number_density = n_e
    transport_data_file = transport_data.txt
    species = 'O2 O2s O2p O Om Op Os'
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    D_mix_names = 'Dmix_flat_O2 Dmix_flat_O2s Dmix_flat_O2p Dmix_flat_O Dmix_flat_Om Dmix_flat_Op Dmix_flat_Os'
    D_T_names = 'DT_flat_O2 DT_flat_O2s DT_flat_O2p DT_flat_O DT_flat_Om DT_flat_Op DT_flat_Os'
    kT_names = 'kT_flat_O2 kT_flat_O2s kT_flat_O2p kT_flat_O kT_flat_Om kT_flat_Op kT_flat_Os'
  []
[]

[FVKernels]
  # ------------------------------------------------------------
  # Signal: real production thermal flux with nonzero grad(T)
  # ------------------------------------------------------------
  [grad_on_reaction]
    type = FVReaction
    variable = probe_grad_on
  []
  [grad_on_thermal]
    type = QPXFVThermalDiffusion
    variable = probe_grad_on
    temperature = T_grad
    thermal_diffusion_coefficient = DT_grad_O
    include_thermal_diffusion = true
  []

  # ------------------------------------------------------------
  # Negative control 1: identical state/profile, switch OFF
  # ------------------------------------------------------------
  [grad_off_reaction]
    type = FVReaction
    variable = probe_grad_off
  []
  [grad_off_thermal]
    type = QPXFVThermalDiffusion
    variable = probe_grad_off
    temperature = T_grad
    thermal_diffusion_coefficient = DT_grad_O
    include_thermal_diffusion = false
  []

  # ------------------------------------------------------------
  # Negative control 2: switch ON, but grad(T)=0
  # ------------------------------------------------------------
  [flat_on_reaction]
    type = FVReaction
    variable = probe_flat_on
  []
  [flat_on_thermal]
    type = QPXFVThermalDiffusion
    variable = probe_flat_on
    temperature = T_flat
    thermal_diffusion_coefficient = DT_flat_O
    include_thermal_diffusion = true
  []
[]

[Postprocessors]
  [T_grad_min]
    type = ElementExtremeValue
    variable = T_grad
    value_type = min
  []
  [T_grad_max]
    type = ElementExtremeValue
    variable = T_grad
    value_type = max
  []
  [T_flat_min]
    type = ElementExtremeValue
    variable = T_flat
    value_type = min
  []
  [T_flat_max]
    type = ElementExtremeValue
    variable = T_flat
    value_type = max
  []

  [DT_grad_O_min]
    type = ElementExtremeValue
    variable = DT_grad_O_aux
    value_type = min
  []
  [DT_grad_O_max]
    type = ElementExtremeValue
    variable = DT_grad_O_aux
    value_type = max
  []
  [DT_flat_O_min]
    type = ElementExtremeValue
    variable = DT_flat_O_aux
    value_type = min
  []
  [DT_flat_O_max]
    type = ElementExtremeValue
    variable = DT_flat_O_aux
    value_type = max
  []

  [probe_grad_on_min]
    type = ElementExtremeValue
    variable = probe_grad_on
    value_type = min
  []
  [probe_grad_on_max]
    type = ElementExtremeValue
    variable = probe_grad_on
    value_type = max
  []
  [probe_grad_on_avg]
    type = ElementAverageValue
    variable = probe_grad_on
  []

  [probe_grad_off_min]
    type = ElementExtremeValue
    variable = probe_grad_off
    value_type = min
  []
  [probe_grad_off_max]
    type = ElementExtremeValue
    variable = probe_grad_off
    value_type = max
  []

  [probe_flat_on_min]
    type = ElementExtremeValue
    variable = probe_flat_on
    value_type = min
  []
  [probe_flat_on_max]
    type = ElementExtremeValue
    variable = probe_flat_on
    value_type = max
  []
[]

[Preconditioning]
  [smp]
    type = SMP
    full = true
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_abs_tol = 1e-13
  nl_rel_tol = 1e-11
  nl_max_its = 20
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
