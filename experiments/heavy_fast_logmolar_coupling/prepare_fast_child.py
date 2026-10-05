#!/usr/bin/env python3
from pathlib import Path

BASE = Path(__file__).parents[1] / "implicit_logmolar_surface_loss" / "input_10step.i"
OUT = Path(__file__).with_name("fast_child.i")

text = BASE.read_text(encoding="utf-8")

# Keep the complete real-QVT mesh so MultiAppCopyTransfer sees the same mesh on
# parent and child. Electron unknowns/kernels remain restricted to block=plasma.
plasma_only = """  [plasma_only]\n    type = BlockDeletionGenerator\n    input = plasma_focus_ring\n    operation = keep\n    block = plasma\n  []\n"""
if plasma_only not in text:
    raise RuntimeError("plasma_only mesh block not found")
text = text.replace(plasma_only, "", 1)

# Heavy pressure/temperature are transferred fields, not local constants.
old_constants = """  [constants]\n    type = ADGenericFunctorMaterial\n    prop_names = 'p T_g carrier_one relative_permittivity n_ion_fixed'\n    prop_values = '1.333223684 300.0 1.0 1.0 1.0e16'\n    block = plasma\n  []\n"""
new_constants = """  [constants]\n    type = ADGenericFunctorMaterial\n    prop_names = 'carrier_one relative_permittivity n_ion_fixed'\n    prop_values = '1.0 1.0 1.0e16'\n    block = plasma\n  []\n"""
if old_constants not in text:
    raise RuntimeError("fast constants block not found")
text = text.replace(old_constants, new_constants, 1)

aux = """
[AuxVariables]
  [p_heavy]
    type = MooseVariableFVReal
    initial_condition = 1.33322
    block = plasma
  []
  [T_g_heavy]
    type = MooseVariableFVReal
    initial_condition = 600.0
    block = plasma
  []
  [rho_heavy_snapshot]
    type = MooseVariableFVReal
    initial_condition = 1.0e-5
    block = plasma
  []
  [w_O2_heavy_snapshot]
    type = MooseVariableFVReal
    initial_condition = 0.70
    block = plasma
  []
  [w_O2s_heavy]
    type = MooseVariableFVReal
    initial_condition = 0.05
    block = plasma
  []
  [w_O2p_heavy]
    type = MooseVariableFVReal
    initial_condition = 0.01
    block = plasma
  []
  [w_O_heavy]
    type = MooseVariableFVReal
    initial_condition = 0.10
    block = plasma
  []
  [w_Om_heavy]
    type = MooseVariableFVReal
    initial_condition = 0.01
    block = plasma
  []
  [w_Op_heavy]
    type = MooseVariableFVReal
    initial_condition = 0.01
    block = plasma
  []
  [w_Os_heavy]
    type = MooseVariableFVReal
    initial_condition = 0.12
    block = plasma
  []
[]

"""
marker = "[FunctorMaterials]\n"
if marker not in text:
    raise RuntimeError("FunctorMaterials marker not found")
text = text.replace(marker, aux + marker, 1)

heavy_materials = """
  # Heavy-flow snapshot reconstruction. These fields are deliberately chemistry-off:
  # they only provide local thermodynamic/composition targets to the fast plasma solve.
  [heavy_O2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2_heavy
    functor_names = 'w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'
    functor_symbols = 's1 s2 s3 s4 s5 s6'
    expression = '1.0-s1-s2-s3-s4-s5-s6'
    block = plasma
  []

  [heavy_mean_molar_mass]
    type = ADParsedFunctorMaterial
    property_name = Mn_mix_heavy
    functor_names = 'w_O2_heavy w_O2s_heavy w_O2p_heavy w_O_heavy w_Om_heavy w_Op_heavy w_Os_heavy'
    functor_symbols = 'm0 m1 m2 m3 m4 m5 m6'
    expression = '1.0/(m0/0.032+m1/0.032+m2/0.032+m3/0.016+m4/0.016+m5/0.016+m6/0.016)'
    block = plasma
  []

  [heavy_density_reconstructed]
    type = ADParsedFunctorMaterial
    property_name = rho_heavy_reconstructed
    functor_names = 'p_heavy Mn_mix_heavy T_g_heavy'
    functor_symbols = 'prs mol tmp'
    expression = 'prs*mol/(8.31446*tmp)'
    block = plasma
  []

  [heavy_O2_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2_heavy
    functor_names = 'rho_heavy_reconstructed w_O2_heavy'
    functor_symbols = 'rho y'
    expression = 'rho*y/0.032'
    block = plasma
  []

  [heavy_O_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O_heavy
    functor_names = 'rho_heavy_reconstructed w_O_heavy'
    functor_symbols = 'rho y'
    expression = 'rho*y/0.016'
    block = plasma
  []

  [heavy_snapshot_checks]
    type = ADParsedFunctorMaterial
    property_name = 'rho_snapshot_rel_error w_O2_snapshot_error'
    functor_names = 'rho_heavy_reconstructed rho_heavy_snapshot w_O2_heavy w_O2_heavy_snapshot'
    functor_symbols = 'rr rs yr ys'
    expression = '(rr-rs)/(rs+1e-300); yr-ys'
    block = plasma
  []

"""
# Place heavy reconstruction before the electron-density materials.
marker2 = "  [electron_molar_density]\n"
if marker2 not in text:
    raise RuntimeError("electron_molar_density marker not found")
text = text.replace(marker2, heavy_materials + marker2, 1)

text = text.replace("    pressure = p\n    gas_temperature = T_g\n", "    pressure = p_heavy\n    gas_temperature = T_g_heavy\n", 1)

# Add child-side transfer validation / concentration diagnostics.
pp_marker = "  [num_dofs]\n"
pp = """  [heavy_p_min]
    type = ADElementExtremeFunctorValue
    functor = p_heavy
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [heavy_p_max]
    type = ADElementExtremeFunctorValue
    functor = p_heavy
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [heavy_Tg_min]
    type = ADElementExtremeFunctorValue
    functor = T_g_heavy
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [heavy_Tg_max]
    type = ADElementExtremeFunctorValue
    functor = T_g_heavy
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [heavy_rho_min]
    type = ADElementExtremeFunctorValue
    functor = rho_heavy_reconstructed
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [heavy_rho_max]
    type = ADElementExtremeFunctorValue
    functor = rho_heavy_reconstructed
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [heavy_cO2_min]
    type = ADElementExtremeFunctorValue
    functor = c_O2_heavy
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [heavy_cO2_max]
    type = ADElementExtremeFunctorValue
    functor = c_O2_heavy
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [heavy_cO_min]
    type = ADElementExtremeFunctorValue
    functor = c_O_heavy
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [heavy_cO_max]
    type = ADElementExtremeFunctorValue
    functor = c_O_heavy
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [rho_snapshot_rel_error_max]
    type = ADElementExtremeFunctorValue
    functor = rho_snapshot_rel_error
    value_type = max_abs
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O2_snapshot_error_max]
    type = ADElementExtremeFunctorValue
    functor = w_O2_snapshot_error
    value_type = max_abs
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []

"""
if pp_marker not in text:
    raise RuntimeError("Postprocessor marker not found")
text = text.replace(pp_marker, pp + pp_marker, 1)

OUT.write_text(text, encoding="utf-8")
print(f"wrote {OUT}")
