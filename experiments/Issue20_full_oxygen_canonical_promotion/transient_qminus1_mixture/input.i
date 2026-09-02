# ==============================================================================
# R14 EVR1-D — seven-species transient heavy-mixture state
#
# Six solved species:
#   O2s O2p O Om Op Os
#
# Constrained species:
#   O2 = 1 - (O2s + O2p + O + Om + Op + Os)
#
# This diagnostic isolates:
#   - Q-1 closure
#   - composition-dependent Mn
#   - rho = p*Mn/(R*T)
#   - transient Mn/rho and chain-rule drho_dt from solved-variable time derivatives
#   - production D_mix-driven mixture-averaged diffusion
#
# Electric migration, Poisson, reactions and bulk advection are intentionally absent.
# Thermal-gradient activation is covered independently by EVR1-C.
#
# IMPORTANT:
# ADParsedFunctorMaterial in the pinned MOOSE build assumes spatial dimension 3.
# The mesh is therefore a thin 3D bar with variation only in x.
# ==============================================================================

[Mesh]
  [mesh]
    type = GeneratedMeshGenerator
    dim = 3
    nx = 12
    ny = 1
    nz = 1
    xmin = 0.0
    xmax = 1.0
    ymin = 0.0
    ymax = 0.01
    zmin = 0.0
    zmax = 0.01
  []
[]

[GlobalParams]
  two_term_boundary_expansion = true
[]

# ==============================================================================
# SIX SOLVED HEAVY MASS FRACTIONS
# ==============================================================================
[Variables]
  [w_O2s]
    type = MooseVariableFVReal
  []
  [w_O2p]
    type = MooseVariableFVReal
  []
  [w_O]
    type = MooseVariableFVReal
  []
  [w_Om]
    type = MooseVariableFVReal
  []
  [w_Op]
    type = MooseVariableFVReal
  []
  [w_Os]
    type = MooseVariableFVReal
  []
[]

# ==============================================================================
# OUTPUT/DERIVATIVE AUX VARIABLES
# ==============================================================================
[AuxVariables]
  [w_O2_out]
    type = MooseVariableFVReal
  []
  [sum_w_out]
    type = MooseVariableFVReal
  []
  [Mn_out]
    type = MooseVariableFVReal
  []
  [rho_out]
    type = MooseVariableFVReal
  []
  [invMn_out]
    type = MooseVariableFVReal
  []
  [dw_O2s_dt]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [dw_O2p_dt]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [dw_O_dt]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [dw_Om_dt]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [dw_Op_dt]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [dw_Os_dt]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

# ==============================================================================
# CONTROLLED INITIAL COMPOSITION
#
# Every solved species is positive. The total solved fraction is safely below 1
# everywhere, so constrained O2 remains positive.
# ==============================================================================
[Functions]
  [ic_O2s]
    type = ParsedFunction
    expression = '0.040 + 0.005*exp(-100.0*(x-0.40)^2)'
  []
  [ic_O2p]
    type = ParsedFunction
    expression = '0.010 + 0.002*exp(-120.0*(x-0.55)^2)'
  []
  [ic_O]
    type = ParsedFunction
    expression = '0.100 + 0.080*exp(-80.0*(x-0.35)^2)'
  []
  [ic_Om]
    type = ParsedFunction
    expression = '0.010 + 0.003*exp(-100.0*(x-0.60)^2)'
  []
  [ic_Op]
    type = ParsedFunction
    expression = '0.010 + 0.003*exp(-90.0*(x-0.50)^2)'
  []
  [ic_Os]
    type = ParsedFunction
    expression = '0.100 + 0.040*exp(-70.0*(x-0.70)^2)'
  []
[]

[ICs]
  [ic_w_O2s]
    type = FunctionIC
    variable = w_O2s
    function = ic_O2s
  []
  [ic_w_O2p]
    type = FunctionIC
    variable = w_O2p
    function = ic_O2p
  []
  [ic_w_O]
    type = FunctionIC
    variable = w_O
    function = ic_O
  []
  [ic_w_Om]
    type = FunctionIC
    variable = w_Om
    function = ic_Om
  []
  [ic_w_Op]
    type = FunctionIC
    variable = w_Op
    function = ic_Op
  []
  [ic_w_Os]
    type = FunctionIC
    variable = w_Os
    function = ic_Os
  []
[]

# ==============================================================================
# Q-1 THERMODYNAMIC CLOSURE + CANONICAL TRANSPORT MATERIAL
# ==============================================================================
[FunctorMaterials]
  [controlled_state]
    type = ADGenericFunctorMaterial
    prop_names = 'p_abs T_g T_e n_e'
    prop_values = '13.332 600.0 20000.0 1.0e16'
  []

  # --------------------------------------------------------------------------
  # Constrained O2:
  #
  #   Y_O2 = 1 - sum_{six solved} Y_k
  #
  # Implemented as an AD functor so the constraint follows current nonlinear
  # iterates rather than a lagged AuxVariable.
  # --------------------------------------------------------------------------
  [O2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2_constraint
    functor_names = 'w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 's1 s2 s3 s4 s5 s6'
    expression = '1.0-s1-s2-s3-s4-s5-s6'
  []

  # --------------------------------------------------------------------------
  # Mean molar mass:
  #
  #   1/Mn = sum_k Y_k/M_k
  #
  # M(O2,O2s,O2p)=0.032 kg/mol
  # M(O,Om,Op,Os)=0.016 kg/mol
  # --------------------------------------------------------------------------
  [mean_molar_mass]
    type = ADParsedFunctorMaterial
    property_name = Mn_mix
    functor_names = 'w_O2_constraint w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 'm0 m1 m2 m3 m4 m5 m6'
    expression = '1.0/(m0/0.032+m1/0.032+m2/0.032+m3/0.016+m4/0.016+m5/0.016+m6/0.016)'
  []

  # --------------------------------------------------------------------------
  # EOS:
  #
  #   rho = p Mn / (R T)
  #
  # R = 8.31446 J/(mol K), matching the validated QPX Step-3 EOS convention.
  # --------------------------------------------------------------------------
  [mixture_density]
    type = ADParsedFunctorMaterial
    property_name = rho_mat
    functor_names = 'p_abs Mn_mix T_g'
    functor_symbols = 'prs mol tmp'
    expression = 'prs*mol/(8.31446*tmp)'
  []

  # --------------------------------------------------------------------------
  # Chain-rule mixture derivatives from the SIX SOLVED nonlinear variables.
  #
  # TimeDerivativeAux is applied directly to w_k, which MOOSE supports.
  # We do NOT differentiate Mn_out/rho_out auxiliary copies.
  #
  # With constrained O2:
  #   dY_O2/dt = -sum_solved dY_s/dt
  #
  # and
  #   d(1/Mn)/dt = sum_k (1/M_k) dY_k/dt.
  #
  # O2, O2s and O2p all have M=0.032 kg/mol, so their constrained
  # contributions cancel. Atomic-family species have M=0.016 kg/mol,
  # yielding (1/0.016 - 1/0.032) = 31.25 mol/kg.
  # --------------------------------------------------------------------------
  [inverse_mean_molar_mass]
    type = ADParsedFunctorMaterial
    property_name = invMn_mix
    functor_names = 'Mn_mix'
    functor_symbols = 'mol'
    expression = '1.0/mol'
  []

  [inverse_mean_molar_mass_dot]
    type = ADParsedFunctorMaterial
    property_name = invMn_dot_model
    functor_names = 'dw_O_dt dw_Om_dt dw_Op_dt dw_Os_dt'
    functor_symbols = 'd3 d4 d5 d6'
    expression = '31.25*(d3+d4+d5+d6)'
  []

  [mean_molar_mass_dot]
    type = ADParsedFunctorMaterial
    property_name = dMn_dt_model
    functor_names = 'Mn_mix dw_O_dt dw_Om_dt dw_Op_dt dw_Os_dt'
    functor_symbols = 'mol d3 d4 d5 d6'
    expression = '-mol*mol*31.25*(d3+d4+d5+d6)'
  []

  [mixture_density_dot]
    type = ADParsedFunctorMaterial
    property_name = drho_dt_model
    functor_names = 'p_abs T_g dMn_dt_model'
    functor_symbols = 'prs tmp dmol'
    expression = 'prs*dmol/(8.31446*tmp)'
  []

  # Exact closure monitor, independent of the transport material's internal
  # sum(Y) guard.
  [sum_w]
    type = ADParsedFunctorMaterial
    property_name = sum_w_functor
    functor_names = 'w_O2_constraint w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 'q0 q1 q2 q3 q4 q5 q6'
    expression = 'q0+q1+q2+q3+q4+q5+q6'
  []

  # Canonical seven-species data-driven transport.
  [heavy_transport]
    type = QPXThermalDiffusionMaterial
    temperature = T_g
    pressure = p_abs
    electron_temperature = T_e
    electron_number_density = n_e
    transport_data_file = transport_data.txt
    species = 'O2 O2s O2p O Om Op Os'
    mass_fractions = 'w_O2_constraint w_O2s w_O2p w_O w_Om w_Op w_Os'
    D_mix_names = 'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'
    D_T_names = 'D_T_O2 D_T_O2s D_T_O2p D_T_O D_T_Om D_T_Op D_T_Os'
    kT_names = 'kT_O2 kT_O2s kT_O2p kT_O kT_Om kT_Op kT_Os'
  []
[]

# ==============================================================================
# AUXILIARY OBSERVABLES
#
# These are output probes only. They do not feed back into the six solved
# transport equations.
# ==============================================================================
[AuxKernels]
  [w_O2_out_aux]
    type = FunctorAux
    variable = w_O2_out
    functor = w_O2_constraint
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [sum_w_out_aux]
    type = FunctorAux
    variable = sum_w_out
    functor = sum_w_functor
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [Mn_out_aux]
    type = FunctorAux
    variable = Mn_out
    functor = Mn_mix
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [rho_out_aux]
    type = FunctorAux
    variable = rho_out
    functor = rho_mat
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [invMn_out_aux]
    type = FunctorAux
    variable = invMn_out
    functor = invMn_mix
    execute_on = 'INITIAL TIMESTEP_END'
  []

  # Direct nonlinear-variable derivatives. This is the supported MOOSE
  # TimeDerivativeAux usage; unlike v1, no derivative is requested from a
  # timestep-end auxiliary copy of Mn or rho.
  [dw_O2s_dt_aux]
    type = TimeDerivativeAux
    variable = dw_O2s_dt
    functor = w_O2s
    execute_on = 'TIMESTEP_END'
  []
  [dw_O2p_dt_aux]
    type = TimeDerivativeAux
    variable = dw_O2p_dt
    functor = w_O2p
    execute_on = 'TIMESTEP_END'
  []
  [dw_O_dt_aux]
    type = TimeDerivativeAux
    variable = dw_O_dt
    functor = w_O
    execute_on = 'TIMESTEP_END'
  []
  [dw_Om_dt_aux]
    type = TimeDerivativeAux
    variable = dw_Om_dt
    functor = w_Om
    execute_on = 'TIMESTEP_END'
  []
  [dw_Op_dt_aux]
    type = TimeDerivativeAux
    variable = dw_Op_dt
    functor = w_Op
    execute_on = 'TIMESTEP_END'
  []
  [dw_Os_dt_aux]
    type = TimeDerivativeAux
    variable = dw_Os_dt
    functor = w_Os
    execute_on = 'TIMESTEP_END'
  []

  # Derived chain-rule outputs are NOT copied by AuxKernels in v4.
  # They are evaluated directly by postprocessors after this AuxKernel stage,
  # eliminating the v3 one-timestep scheduling lag.
[]

# ==============================================================================
# SIX TRANSIENT PRODUCTION SPECIES EQUATIONS
#
#   rho dY_k/dt
#     + div[-rho D_km(grad Y_k + Y_k/Mn grad Mn)] = 0
#
# No bulk advection, reactions, migration, or Poisson in EVR1-D.
# ==============================================================================
[FVKernels]
  [O2s_time]
    type = QPXFVMassFractionTimeDerivative
    variable = w_O2s
    rho = rho_mat
  []
  [O2s_diff]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_O2s
    rho = rho_mat
    diffusivity = D_mix_O2s
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []

  [O2p_time]
    type = QPXFVMassFractionTimeDerivative
    variable = w_O2p
    rho = rho_mat
  []
  [O2p_diff]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_O2p
    rho = rho_mat
    diffusivity = D_mix_O2p
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []

  [O_time]
    type = QPXFVMassFractionTimeDerivative
    variable = w_O
    rho = rho_mat
  []
  [O_diff]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_O
    rho = rho_mat
    diffusivity = D_mix_O
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []

  [Om_time]
    type = QPXFVMassFractionTimeDerivative
    variable = w_Om
    rho = rho_mat
  []
  [Om_diff]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_Om
    rho = rho_mat
    diffusivity = D_mix_Om
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []

  [Op_time]
    type = QPXFVMassFractionTimeDerivative
    variable = w_Op
    rho = rho_mat
  []
  [Op_diff]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_Op
    rho = rho_mat
    diffusivity = D_mix_Op
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []

  [Os_time]
    type = QPXFVMassFractionTimeDerivative
    variable = w_Os
    rho = rho_mat
  []
  [Os_diff]
    type = QPXFVMixtureAveragedDiffusion
    variable = w_Os
    rho = rho_mat
    diffusivity = D_mix_Os
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []
[]

# Natural FV boundaries provide the closed zero-normal-flux control.

# ==============================================================================
# OBSERVABLES
# ==============================================================================
[Postprocessors]
  # Solved species bounds and activity
  [w_O2s_avg]
    type = ElementAverageValue
    variable = w_O2s
  []
  [w_O2s_min]
    type = ElementExtremeValue
    variable = w_O2s
    value_type = min
  []
  [w_O2s_max]
    type = ElementExtremeValue
    variable = w_O2s
    value_type = max
  []

  [w_O2p_avg]
    type = ElementAverageValue
    variable = w_O2p
  []
  [w_O2p_min]
    type = ElementExtremeValue
    variable = w_O2p
    value_type = min
  []
  [w_O2p_max]
    type = ElementExtremeValue
    variable = w_O2p
    value_type = max
  []

  [w_O_avg]
    type = ElementAverageValue
    variable = w_O
  []
  [w_O_min]
    type = ElementExtremeValue
    variable = w_O
    value_type = min
  []
  [w_O_max]
    type = ElementExtremeValue
    variable = w_O
    value_type = max
  []

  [w_Om_avg]
    type = ElementAverageValue
    variable = w_Om
  []
  [w_Om_min]
    type = ElementExtremeValue
    variable = w_Om
    value_type = min
  []
  [w_Om_max]
    type = ElementExtremeValue
    variable = w_Om
    value_type = max
  []

  [w_Op_avg]
    type = ElementAverageValue
    variable = w_Op
  []
  [w_Op_min]
    type = ElementExtremeValue
    variable = w_Op
    value_type = min
  []
  [w_Op_max]
    type = ElementExtremeValue
    variable = w_Op
    value_type = max
  []

  [w_Os_avg]
    type = ElementAverageValue
    variable = w_Os
  []
  [w_Os_min]
    type = ElementExtremeValue
    variable = w_Os
    value_type = min
  []
  [w_Os_max]
    type = ElementExtremeValue
    variable = w_Os
    value_type = max
  []

  # Constrained O2 and exact mass closure
  [w_O2_avg]
    type = ElementAverageValue
    variable = w_O2_out
  []
  [w_O2_min]
    type = ElementExtremeValue
    variable = w_O2_out
    value_type = min
  []
  [w_O2_max]
    type = ElementExtremeValue
    variable = w_O2_out
    value_type = max
  []

  [sum_w_min]
    type = ElementExtremeValue
    variable = sum_w_out
    value_type = min
  []
  [sum_w_max]
    type = ElementExtremeValue
    variable = sum_w_out
    value_type = max
  []

  # Mn and rho
  [Mn_avg]
    type = ElementAverageValue
    variable = Mn_out
  []
  [Mn_min]
    type = ElementExtremeValue
    variable = Mn_out
    value_type = min
  []
  [Mn_max]
    type = ElementExtremeValue
    variable = Mn_out
    value_type = max
  []

  [rho_avg]
    type = ElementAverageValue
    variable = rho_out
  []
  [rho_min]
    type = ElementExtremeValue
    variable = rho_out
    value_type = min
  []
  [rho_max]
    type = ElementExtremeValue
    variable = rho_out
    value_type = max
  []

  [invMn_avg]
    type = ElementAverageValue
    variable = invMn_out
  []
  [invMn_min]
    type = ElementExtremeValue
    variable = invMn_out
    value_type = min
  []
  [invMn_max]
    type = ElementExtremeValue
    variable = invMn_out
    value_type = max
  []

  # IMPORTANT v4 ordering fix:
  # These derived functors are evaluated in the postprocessor stage, AFTER
  # timestep-end TimeDerivativeAux kernels have updated the direct dw_k/dt
  # auxiliary fields. This removes the v3 same-stage one-timestep lag.
  [invMn_dot_avg]
    type = ElementAverageFunctorPostprocessor
    functor = invMn_dot_model
  []

  [dMn_dt_avg]
    type = ElementAverageFunctorPostprocessor
    functor = dMn_dt_model
  []

  [drho_dt_avg]
    type = ElementAverageFunctorPostprocessor
    functor = drho_dt_model
  []

  # Direct species time-derivative activity discriminators.
  [dw_O_avg]
    type = ElementAverageValue
    variable = dw_O_dt
  []
  [dw_Om_avg]
    type = ElementAverageValue
    variable = dw_Om_dt
  []
  [dw_Op_avg]
    type = ElementAverageValue
    variable = dw_Op_dt
  []
  [dw_Os_avg]
    type = ElementAverageValue
    variable = dw_Os_dt
  []

  [dw_O_dt_min]
    type = ElementExtremeValue
    variable = dw_O_dt
    value_type = min
  []
  [dw_O_dt_max]
    type = ElementExtremeValue
    variable = dw_O_dt
    value_type = max
  []
  [dw_Os_dt_min]
    type = ElementExtremeValue
    variable = dw_Os_dt
    value_type = min
  []
  [dw_Os_dt_max]
    type = ElementExtremeValue
    variable = dw_Os_dt
    value_type = max
  []

  # Canonical D_mix remains live during the transient solve.
  [Dmix_O2_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_O2
  []
  [Dmix_O2s_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_O2s
  []
  [Dmix_O2p_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_O2p
  []
  [Dmix_O_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_O
  []
  [Dmix_Om_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_Om
  []
  [Dmix_Op_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_Op
  []
  [Dmix_Os_avg]
    type = ElementAverageFunctorPostprocessor
    functor = D_mix_Os
  []
[]

[Preconditioning]
  [smp]
    type = SMP
    full = true
  []
[]

[Executioner]
  type = Transient
  solve_type = NEWTON

  dt = 1.0e-4
  end_time = 5.0e-4

  nl_abs_tol = 1.0e-11
  nl_rel_tol = 1.0e-8
  nl_max_its = 30

  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
[]

[Outputs]
  csv = true
[]
