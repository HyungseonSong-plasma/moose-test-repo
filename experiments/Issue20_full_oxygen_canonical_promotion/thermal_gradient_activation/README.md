# R14 EVR1-C — thermal-gradient activation

This diagnostic uses the actual production `QPXFVThermalDiffusion` kernel.

Three-way localization:

1. `probe_grad_on`
   - nonlinear T(x)
   - production D_T,O from QPXThermalDiffusionMaterial
   - include_thermal_diffusion=true
   - expected: nonzero response

2. `probe_grad_off`
   - identical nonlinear T(x) and production D_T,O
   - include_thermal_diffusion=false
   - expected: zero response

3. `probe_flat_on`
   - T=600 K
   - production D_T,O
   - include_thermal_diffusion=true
   - expected: zero response

The `FVReaction` term is only an observation sink: it turns the prescribed
thermal-flux divergence into a unique steady probe response. It is not claimed
as a physical heavy-species source term.

Transport-data SHA-256:
`2fa7988c79f6ea23ebdd50e6d1d7fc5018dc8854a27459511ec95c94ebe7ff3d`

Run from qpx/temp:

    ./run_test.sh heavy_transport/r14_thermal_flux_evr1c
