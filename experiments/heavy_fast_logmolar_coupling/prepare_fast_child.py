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

old_constants = """  [constants]\n    type = ADGenericFunctorMaterial\n    prop_names = 'p T_g carrier_one relative_permittivity n_ion_fixed'\n    prop_values = '1.333223684 300.0 1.0 1.0 1.0e16'\n    block = plasma\n  []\n"""
new_constants = """  [constants]\n    type = ADGenericFunctorMaterial\n    prop_names = 'carrier_one relative_permittivity n_ion_fixed'\n    prop_values = '1.0 1.0 1.0e16'\n    block = plasma\n  []\n"""
if old_constants not in text:
    raise RuntimeError("fast constants block not found")
text = text.replace(old_constants, new_constants, 1)

heavy_vars = [
    ("p_heavy", "1.33322"),
    ("T_g_heavy", "600.0"),
    ("rho_heavy_snapshot", "1.0e-5"),
    ("w_O2_heavy_snapshot", "0.70"),
    ("w_O2s_heavy", "0.05"),
    ("w_O2p_heavy", "0.01"),
    ("w_O_heavy", "0.10"),
    ("w_Om_heavy", "0.01"),
    ("w_Op_heavy", "0.01"),
    ("w_Os_heavy", "0.12"),
]
aux = "[AuxVariables]\n"
for name, ic in heavy_vars:
    aux += f"  [{name}]\n    type = MooseVariableFVReal\n    initial_condition = {ic}\n    block = plasma\n  []\n"
aux += "[]\n\n"
if "[FunctorMaterials]\n" not in text:
    raise RuntimeError("FunctorMaterials marker not found")
text = text.replace("[FunctorMaterials]\n", aux + "[FunctorMaterials]\n", 1)

heavy_materials = """
  # Heavy-flow snapshot reconstruction. Chemistry remains off in this coupling gate.
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
  [rho_snapshot_check]
    type = ADParsedFunctorMaterial
    property_name = rho_snapshot_rel_error
    functor_names = 'rho_heavy_reconstructed rho_heavy_snapshot'
    functor_symbols = 'rr rs'
    expression = '(rr-rs)/(rs+1e-300)'
    block = plasma
  []
  [O2_snapshot_check]
    type = ADParsedFunctorMaterial
    property_name = w_O2_snapshot_error
    functor_names = 'w_O2_heavy w_O2_heavy_snapshot'
    functor_symbols = 'yr ys'
    expression = 'yr-ys'
    block = plasma
  []

"""
marker = "  [electron_molar_density]\n"
if marker not in text:
    raise RuntimeError("electron_molar_density marker not found")
text = text.replace(marker, heavy_materials + marker, 1)
text = text.replace("    pressure = p\n    gas_temperature = T_g\n", "    pressure = p_heavy\n    gas_temperature = T_g_heavy\n", 1)

pps = [
    ("heavy_p_min", "p_heavy", "min"), ("heavy_p_max", "p_heavy", "max"),
    ("heavy_Tg_min", "T_g_heavy", "min"), ("heavy_Tg_max", "T_g_heavy", "max"),
    ("heavy_rho_min", "rho_heavy_reconstructed", "min"), ("heavy_rho_max", "rho_heavy_reconstructed", "max"),
    ("heavy_cO2_min", "c_O2_heavy", "min"), ("heavy_cO2_max", "c_O2_heavy", "max"),
    ("heavy_cO_min", "c_O_heavy", "min"), ("heavy_cO_max", "c_O_heavy", "max"),
    ("rho_snapshot_rel_error_max", "rho_snapshot_rel_error", "max_abs"),
    ("w_O2_snapshot_error_max", "w_O2_snapshot_error", "max_abs"),
]
pp = ""
for name, functor, value_type in pps:
    pp += f"  [{name}]\n    type = ADElementExtremeFunctorValue\n    functor = {functor}\n    value_type = {value_type}\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n"
pp += "\n"
marker = "  [num_dofs]\n"
if marker not in text:
    raise RuntimeError("Postprocessor marker not found")
text = text.replace(marker, pp + marker, 1)

OUT.write_text(text, encoding="utf-8")
print(f"wrote {OUT}")
