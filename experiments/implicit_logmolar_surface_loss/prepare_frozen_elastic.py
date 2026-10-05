#!/usr/bin/env python3
from pathlib import Path

BASE = Path(__file__).with_name("input_10step.i")
OUT = Path(__file__).with_name("input_10step_frozen_elastic.i")

# Frozen heavy composition taken from the accepted heavy-base inlet/reference state.
# Full composition is used to recover the mixture molar mass; only ground-state O2 and O
# are retained as elastic collision targets in this diagnostic.
P_PA = 1.333223684
T_K = 300.0
R_GAS = 8.31446
N_A = 6.02214076e23
M_E = 9.1093837139e-31
K_B_OVER_E = 8.617333262145e-5

Y = {
    "O2": 0.70,
    "O2s": 0.05,
    "O2p": 0.01,
    "O": 0.10,
    "Om": 0.01,
    "Op": 0.01,
    "Os": 0.12,
}
M = {name: (0.032 if name.startswith("O2") else 0.016) for name in Y}
INV_MMIX = sum(Y[name] / M[name] for name in Y)
M_MIX = 1.0 / INV_MMIX
C_TOTAL = P_PA / (R_GAS * T_K)
X_O2 = (Y["O2"] / M["O2"]) / INV_MMIX
X_O = (Y["O"] / M["O"]) / INV_MMIX
C_O2 = X_O2 * C_TOTAL
C_O = X_O * C_TOTAL
N_O2 = C_O2 * N_A
N_O = C_O * N_A

# Delta epsilon = alpha * [(2/3)<epsilon> - (kB/e) Tg], eV per collision.
ALPHA_O2 = 3.0 * M_E / (31.998e-3 / N_A)
ALPHA_O = 3.0 * M_E / (15.999e-3 / N_A)

text = BASE.read_text(encoding="utf-8")
text = text.replace(
    "# Surface electron/energy loss is the only mechanism that initially separates charge.\n",
    "# Surface electron/energy loss is the only mechanism that initially separates charge.\n"
    "# Frozen O2/O elastic electron-heavy energy exchange is included in the bulk.\n"
    f"# Frozen mixture: Mmix={M_MIX:.17g} kg/mol, c_O2={C_O2:.17g} mol/m^3, "
    f"c_O={C_O:.17g} mol/m^3.\n",
)

marker = "  [charge_number_density]\n"
insert = f"""  [frozen_heavy_targets]\n    type = ADGenericFunctorMaterial\n    prop_names = 'c_O2_frozen c_O_frozen'\n    prop_values = '{C_O2:.17g} {C_O:.17g}'\n    block = plasma\n  []\n\n  [elastic_O2_rate]\n    type = PhysicsElectronImpactRateMaterial\n    rate_table_file = '../../physics_app/data/electron_impact/o2_elastic.txt'\n    mean_energy = mean_en_solved\n    electron_number_density = n_e_physical\n    target_molar_concentration = c_O2_frozen\n    reaction_progress = R_elastic_O2\n    block = plasma\n  []\n\n  [elastic_O_rate]\n    type = PhysicsElectronImpactRateMaterial\n    rate_table_file = '../../physics_app/data/electron_impact/o_elastic.txt'\n    mean_energy = mean_en_solved\n    electron_number_density = n_e_physical\n    target_molar_concentration = c_O_frozen\n    reaction_progress = R_elastic_O\n    block = plasma\n  []\n\n  # log_energy advances q_eps=w_e/N_A [eV mol/m^3], so these sources are\n  # S_mol=-Delta_epsilon*R_elastic [eV mol/(m^3 s)] with NO extra N_A factor.\n  [elastic_O2_energy_source]\n    type = ADParsedFunctorMaterial\n    property_name = S_elastic_O2_molar\n    functor_names = 'mean_en_solved T_g R_elastic_O2'\n    functor_symbols = 'meanE tgas rprog'\n    expression = '-{ALPHA_O2:.17g}*(0.66666666666666663*meanE-{K_B_OVER_E:.17g}*tgas)*rprog'\n    block = plasma\n  []\n\n  [elastic_O_energy_source]\n    type = ADParsedFunctorMaterial\n    property_name = S_elastic_O_molar\n    functor_names = 'mean_en_solved T_g R_elastic_O'\n    functor_symbols = 'meanE tgas rprog'\n    expression = '-{ALPHA_O:.17g}*(0.66666666666666663*meanE-{K_B_OVER_E:.17g}*tgas)*rprog'\n    block = plasma\n  []\n\n  [elastic_total_energy_source]\n    type = ADParsedFunctorMaterial\n    property_name = S_elastic_total_molar\n    functor_names = 'S_elastic_O2_molar S_elastic_O_molar'\n    functor_symbols = 'sO2 sO'\n    expression = 'sO2+sO'\n    block = plasma\n  []\n\n"""
if marker not in text:
    raise RuntimeError("FunctorMaterials insertion marker not found")
text = text.replace(marker, insert + marker, 1)

kernel_marker = "\n  [phi_diffusion]\n"
kernel_insert = """
  [energy_elastic_O2]\n    type = FVCoupledForce\n    variable = log_energy\n    v = S_elastic_O2_molar\n    coef = 1.0\n    block = plasma\n  []\n  [energy_elastic_O]\n    type = FVCoupledForce\n    variable = log_energy\n    v = S_elastic_O_molar\n    coef = 1.0\n    block = plasma\n  []\n"""
if kernel_marker not in text:
    raise RuntimeError("FVKernels insertion marker not found")
text = text.replace(kernel_marker, kernel_insert + kernel_marker, 1)

pp_marker = "  [charge_integral]\n"
pp_insert = """  [elastic_O2_rate_avg]\n    type = ElementAverageFunctorPostprocessor\n    functor = R_elastic_O2\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [elastic_O_rate_avg]\n    type = ElementAverageFunctorPostprocessor\n    functor = R_elastic_O\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [elastic_source_avg]\n    type = ElementAverageFunctorPostprocessor\n    functor = S_elastic_total_molar\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [elastic_source_integral]\n    type = ADElementIntegralFunctorPostprocessor\n    functor = S_elastic_total_molar\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n\n"""
if pp_marker not in text:
    raise RuntimeError("Postprocessor insertion marker not found")
text = text.replace(pp_marker, pp_insert + pp_marker, 1)

OUT.write_text(text, encoding="utf-8")
print(f"wrote {OUT}")
print(f"M_mix={M_MIX:.12g} kg/mol")
print(f"c_total={C_TOTAL:.12g} mol/m^3")
print(f"c_O2={C_O2:.12g} mol/m^3, n_O2={N_O2:.12g} 1/m^3")
print(f"c_O={C_O:.12g} mol/m^3, n_O={N_O:.12g} 1/m^3")
print(f"alpha_O2={ALPHA_O2:.12g}, alpha_O={ALPHA_O:.12g}")
