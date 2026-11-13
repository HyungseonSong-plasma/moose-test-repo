# Synthetic Native P2: 2-D flow BCs are generated from SCCM and inlet area.
# This is not a scientific P3 fluid-flow parity claim.
[Mesh]
  type = GeneratedMesh
  dim = 2
  nx = 2
  ny = 2
[]
[Problem]
  solve = false
  kernel_coverage_check = false
[]
[Variables]
  [p_flow]
    type = INSFVPressureVariable
    initial_condition = 1.333223684
  []
  [u]
    type = INSFVVelocityVariable
    initial_condition = 0
  []
  [v]
    type = INSFVVelocityVariable
    initial_condition = 0
  []
  [w_O2]
    type = MooseVariableFVReal
  []
  [w_O]
    type = MooseVariableFVReal
  []
[]
[Physics]
  [Plasmas]
    files = json_surface_rate_p2.json
    pressure = 1.333223684
    temperature = 300
    state_model = ideal_gas
    sccm = 100
    inlet_boundaries = left
    inlet_flow_variables = 'p_flow u v'
    inlet_flow_direction = '-1 0 0'
  []
[]
[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
