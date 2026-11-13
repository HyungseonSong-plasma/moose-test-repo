# P2 only: JSON + Physics generate electron continuity/energy states, conservative
# time, drift-diffusion, Joule, mean-energy and sheath flux providers, plus BCs.
# No physical time integration or scientific parity assertion.
# GeneratedMesh sideset mapping: left=wafer, bottom=cover, right=inlet, top=outlet.
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
  [potential]
    type = MooseVariable
  []
[]
[Physics]
  [Plasmas]
    files = dd_plasma_boundary_json_p2.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          fem_species = 'e 1e15'
          fem_potential = potential
        []
        [Energy]
          fem_species = e
          fem_potential = potential
          initial_molar_energy_density_eV = 8.3e-9
        []
      []
    []
  []
[]
[Executioner]
  type = Transient
  dt = 1
  num_steps = 1
[]
