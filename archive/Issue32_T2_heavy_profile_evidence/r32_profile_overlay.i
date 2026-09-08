# Issue #32 diagnostic overlay.
# No physics coefficients, dt, tolerances, BCs, or solver type are changed.

[Postprocessors]
  [r32_num_dofs]
    type = NumDOFs
    system = NL
    execute_on = 'initial timestep_end'
  []
  [r32_nonlinear_iterations]
    type = NumNonlinearIterations
    execute_on = timestep_end
  []
  [r32_linear_iterations]
    type = NumLinearIterations
    execute_on = timestep_end
  []
  [r32_residual_evaluations]
    type = NumResidualEvaluations
    execute_on = timestep_end
  []
[]

[Outputs]
  [r32_perfgraph]
    type = PerfGraphOutput
    execute_on = final
    level = 3
    heaviest_branch = true
    heaviest_sections = 40
  []
  [r32_metrics]
    type = CSV
    file_base = '/home/songhyeongseon/projects/qvt3d/qpx/temp/r32_full_bundle_builder/r32_full_profile_case/case/r32_profiles/T2-heavy_20260828T075225Z/r32_metrics'
    show = 'r32_num_dofs r32_nonlinear_iterations r32_linear_iterations r32_residual_evaluations'
    execute_on = 'initial timestep_end'
  []
[]
