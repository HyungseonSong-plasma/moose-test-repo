#!/usr/bin/env python3
import math
import os
from pathlib import Path

BASE = Path(__file__).parents[1] / "implicit_logmolar_surface_loss" / "input_10step.i"
OUT = Path(__file__).with_name("fast_child.i")
text = BASE.read_text(encoding="utf-8")

AVOGADRO = 6.02214076e23
MEAN_ELECTRON_ENERGY_EV = 5.73276
STARTUP_RHO = float(os.environ.get("STARTUP_RHO", "7.01e-6"))
W_O2P_INITIAL = 7.580404957618788e-5
W_OM_INITIAL = 0.0
W_OP_INITIAL = 0.0

# Enforce quasi-neutral startup from the same heavy-species state used by the
# Poisson charge closure. All charged heavy species are singly charged here.
n_O2p_initial = AVOGADRO * STARTUP_RHO * W_O2P_INITIAL / 0.032
n_Om_initial = AVOGADRO * STARTUP_RHO * W_OM_INITIAL / 0.016
n_Op_initial = AVOGADRO * STARTUP_RHO * W_OP_INITIAL / 0.016
n_e_initial = n_O2p_initial + n_Op_initial - n_Om_initial
if n_e_initial <= 0.0:
    raise RuntimeError(f"non-positive quasi-neutral electron IC: {n_e_initial}")

electron_molar_ic = n_e_initial / AVOGADRO
log_ne_ic = math.log(electron_molar_ic)
log_energy_ic = math.log(electron_molar_ic * MEAN_ELECTRON_ENERGY_EV)

old_electron_ics = """  [log_ne]\n    type = MooseVariableFVReal\n    initial_condition = -17.91353845503591\n    block = plasma\n  []\n  [log_energy]\n    type = MooseVariableFVReal\n    initial_condition = -16.16734136488706\n    block = plasma\n  []\n"""
new_electron_ics = f"""  [log_ne]\n    type = MooseVariableFVReal\n    initial_condition = {log_ne_ic:.17g}\n    block = plasma\n  []\n  [log_energy]\n    type = MooseVariableFVReal\n    initial_condition = {log_energy_ic:.17g}\n    block = plasma\n  []\n"""
if old_electron_ics not in text:
    raise RuntimeError("electron IC block not found")
text = text.replace(old_electron_ics, new_electron_ics, 1)

# Keep the complete real-QVT mesh so MultiAppCopyTransfer sees the same mesh on
# parent and child. Electron unknowns/kernels remain restricted to block=plasma.
plasma_only = """  [plasma_only]\n    type = BlockDeletionGenerator\n    input = plasma_focus_ring\n    operation = keep\n    block = plasma\n  []\n"""
if plasma_only not in text:
    raise RuntimeError("plasma_only mesh block not found")
text = text.replace(plasma_only, "", 1)

# Fast plasma now receives p, Tg, density and charged-heavy fractions from the
# heavy parent. No fixed ion density remains in the Poisson closure.
old_constants = """  [constants]\n    type = ADGenericFunctorMaterial\n    prop_names = 'p T_g carrier_one relative_permittivity n_ion_fixed'\n    prop_values = '1.333223684 300.0 1.0 1.0 1.0e16'\n    block = plasma\n  []\n"""
new_constants = """  [constants]\n    type = ADGenericFunctorMaterial\n    prop_names = 'carrier_one relative_permittivity'\n    prop_values = '1.0 1.0'\n    block = plasma\n  []\n  [inactive_mesh_blocks]\n    type = ADGenericFunctorMaterial\n    prop_names = 'coupling_dummy'\n    prop_values = '0.0'\n    block = 'wafer cover focus_ring coil1 coil2 coil3 electrode top vacuum metal right bottom port'\n  []\n"""
if old_constants not in text:
    raise RuntimeError("fast constants block not found")
text = text.replace(old_constants, new_constants, 1)

# Initial values only seed the child before the first transfer. The parent owns
# the live values from then on. Electron density is derived from this exact
# charged-heavy state so the child starts quasi-neutral by construction.
heavy_vars = [
    ("p_heavy", "1.33322"),
    ("T_g_heavy", "600.0"),
    ("rho_heavy_snapshot", f"{STARTUP_RHO:.17g}"),
    ("w_O2_heavy_snapshot", "0.7299241959504238"),
    ("w_O2s_heavy", "0.05"),
    ("w_O2p_heavy", f"{W_O2P_INITIAL:.17g}"),
    ("w_O_heavy", "0.10"),
    ("w_Om_heavy", f"{W_OM_INITIAL:.17g}"),
    ("w_Op_heavy", f"{W_OP_INITIAL:.17g}"),
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
  # Heavy-flow state reconstructed from transferred pressure, temperature,
  # density, and species mass fractions. Chemistry remains disabled here.
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
    functor_names = 'rho_heavy_snapshot w_O2_heavy'
    functor_symbols = 'rhv frac'
    expression = 'rhv*frac/0.032'
    block = plasma
  []
  [heavy_O_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O_heavy
    functor_names = 'rho_heavy_snapshot w_O_heavy'
    functor_symbols = 'rhv frac'
    expression = 'rhv*frac/0.016'
    block = plasma
  []
  [heavy_O2p_number_density]
    type = ADParsedFunctorMaterial
    property_name = n_O2p_heavy
    functor_names = 'rho_heavy_snapshot w_O2p_heavy'
    functor_symbols = 'rhv frac'
    expression = '6.02214076e23*rhv*frac/0.032'
    block = plasma
  []
  [heavy_Om_number_density]
    type = ADParsedFunctorMaterial
    property_name = n_Om_heavy
    functor_names = 'rho_heavy_snapshot w_Om_heavy'
    functor_symbols = 'rhv frac'
    expression = '6.02214076e23*rhv*frac/0.016'
    block = plasma
  []
  [heavy_Op_number_density]
    type = ADParsedFunctorMaterial
    property_name = n_Op_heavy
    functor_names = 'rho_heavy_snapshot w_Op_heavy'
    functor_symbols = 'rhv frac'
    expression = '6.02214076e23*rhv*frac/0.016'
    block = plasma
  []
  [heavy_positive_ion_density]
    type = ADParsedFunctorMaterial
    property_name = n_positive_heavy
    functor_names = 'n_O2p_heavy n_Op_heavy'
    functor_symbols = 'n1 n2'
    expression = 'n1+n2'
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

old_charge = """  [charge_number_density]\n    type = ADParsedFunctorMaterial\n    property_name = charge_number_density\n    functor_names = 'n_ion_fixed n_e_physical'\n    functor_symbols = 'ni ne'\n    expression = 'ni-ne'\n    block = plasma\n  []\n"""
new_charge = """  [charge_number_density]\n    type = ADParsedFunctorMaterial\n    property_name = charge_number_density\n    functor_names = 'n_O2p_heavy n_Op_heavy n_Om_heavy n_e_physical'\n    functor_symbols = 'nO2p nOp nOm ne'\n    expression = 'nO2p+nOp-nOm-ne'\n    block = plasma\n  []\n"""
if old_charge not in text:
    raise RuntimeError("fixed-ion charge closure not found")
text = text.replace(old_charge, new_charge, 1)

pps = [
    ("heavy_p_min", "p_heavy", "min"), ("heavy_p_max", "p_heavy", "max"),
    ("heavy_Tg_min", "T_g_heavy", "min"), ("heavy_Tg_max", "T_g_heavy", "max"),
    ("heavy_rho_min", "rho_heavy_snapshot", "min"), ("heavy_rho_max", "rho_heavy_snapshot", "max"),
    ("heavy_cO2_min", "c_O2_heavy", "min"), ("heavy_cO2_max", "c_O2_heavy", "max"),
    ("heavy_cO_min", "c_O_heavy", "min"), ("heavy_cO_max", "c_O_heavy", "max"),
    ("n_O2p_min", "n_O2p_heavy", "min"), ("n_O2p_max", "n_O2p_heavy", "max"),
    ("rho_snapshot_rel_error_max", "rho_snapshot_rel_error", "max_abs"),
    ("w_O2_snapshot_error_max", "w_O2_snapshot_error", "max_abs"),
]
pp = ""
for name, functor, value_type in pps:
    pp += f"  [{name}]\n    type = ADElementExtremeFunctorValue\n    functor = {functor}\n    value_type = {value_type}\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n"
pp += """
  [positive_ion_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_positive_heavy
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []

"""
marker = "  [num_dofs]\n"
if marker not in text:
    raise RuntimeError("Postprocessor marker not found")
text = text.replace(marker, pp + marker, 1)

if "n_ion_fixed" in text:
    raise RuntimeError("fast child still contains fixed ion density")

OUT.write_text(text, encoding="utf-8")
print(f"wrote {OUT}")
print(
    "quasi-neutral startup: "
    f"rho={STARTUP_RHO:.17g}, n_O2p={n_O2p_initial:.17g}, "
    f"n_Op={n_Op_initial:.17g}, n_Om={n_Om_initial:.17g}, "
    f"n_e={n_e_initial:.17g}, log_ne={log_ne_ic:.17g}, "
    f"log_energy={log_energy_ic:.17g}"
)
