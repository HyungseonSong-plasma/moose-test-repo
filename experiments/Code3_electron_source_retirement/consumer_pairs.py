"""Code3 #817: old/candidate source input pairs for H05, R2, S5-R."""
from pathlib import Path
from experiments.Code3_electron_source_retirement import run as code3
from physics_app.ci import check_stage5_h05_runtime as h05
from physics_app.ci import check_r2_o2_ionization_implementation as r2
from physics_app.ci.check_issue402_json_rate_native_p2 import (
    migrate_h05_physical_energy_to_log_molar_scratch,
)

ROOT = Path(__file__).resolve().parents[2]
H05_TARGET = R2_TARGET = "FVKernels/n_e_source"
S5R_TARGET = "FVKernels/s5r_electron_source"
_R2_OLD = '''  [mean_energy_bridge]
    type = ElectronEnergyMaterial
    electron_energy_density = mean_en
    electron_density = n_e
    state_form = physical_eV
  []'''
_R2_NEW = '''  [r2_log_molar_density]
    type = ADParsedFunctorMaterial
    property_name = r2_log_molar_density
    functor_names = 'n_e'
    functor_symbols = 'ne'
    expression = 'log(ne/6.02214076e23)'
  []
  [r2_log_molar_energy]
    type = ADParsedFunctorMaterial
    property_name = r2_log_molar_energy
    functor_names = 'mean_en'
    functor_symbols = 'energy'
    expression = 'log(energy/6.02214076e23)'
  []
  [mean_energy_bridge]
    type = ElectronEnergyMaterial
    electron_energy_density = r2_log_molar_energy
    electron_density = r2_log_molar_density
    state_form = log_molar_eV
  []'''

def r2_energy_bridge(text: str) -> str:
    """Upgrade BOTH arms' historical energy representation identically."""
    if text.count(_R2_OLD) != 1 or text.count("state_form = physical_eV") != 1:
        raise code3.Code3ParityError("R2_BRIDGE_SOURCE_DRIFT")
    updated = text.replace(_R2_OLD, _R2_NEW)
    if updated.count("state_form = log_molar_eV") != 1 or "physical_eV" in updated:
        raise code3.Code3ParityError("R2_BRIDGE_INVALID")
    return updated

def pair(original: str, target: str, functor: str, mode: str):
    candidate, info = code3.replace_electron_only(original, path=target)
    if code3._outside_target(original, target) != code3._outside_target(candidate, target):
        raise code3.Code3ParityError("NON_ELECTRON_BYTES_CHANGED")
    if info["source_functor"] != functor or info["mode"] != mode:
        raise code3.Code3ParityError("SOURCE_BINDING_CHANGED")
    if mode == "physical" and info["coefficient"] != 1.0:
        raise code3.Code3ParityError("PHYSICAL_COEFFICIENT_CHANGED")
    if mode == "normalized" and not (0.0 < info["coefficient"] < 1.0):
        raise code3.Code3ParityError("NORMALIZED_COEFFICIENT_CHANGED")
    return original, candidate, info

def h05_pair():
    old = migrate_h05_physical_energy_to_log_molar_scratch(h05.runtime_input())
    return pair(old, H05_TARGET, "S_e_h05", "physical")

def r2_pair():
    old = r2_energy_bridge(r2.RUNTIME_INPUT)
    return pair(old, R2_TARGET, "electron_ionization_number_source", "physical")

def s5r_pair():
    from experiments.historical_recipe_support.issue192_s5r import (
        build_s5r_input, audit_s5r_input,
    )
    base = (ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i").read_text()
    old, meta = build_s5r_input(base)
    if audit_s5r_input(old)["status"] != "PASS" or meta["audit"]["status"] != "PASS":
        raise code3.Code3ParityError("S5R_ORIGINAL_INPUT_AUDIT_FAILED")
    return pair(old, S5R_TARGET, "S_e_s5r", "normalized")
