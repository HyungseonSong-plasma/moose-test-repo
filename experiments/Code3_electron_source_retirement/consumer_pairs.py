"""Code3 #817: old/candidate source input pairs for H05, R2, S5-R."""
import math
from pathlib import Path
from physics_harness.adapters.moose import parameters as mp
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

def virtual_legacy_from_current(actual: str, target: str, functor: str, mode: str) -> str:
    """Synthetic historical A/B arm; only current standard arm is runnable after source cut."""
    typ = mp.get_parameter(actual, target, "type")
    if typ == code3.OLD:
        return actual
    if typ != code3.NEW or mp.get_parameter(actual, target, "v") != functor:
        raise code3.Code3ParityError("CURRENT_RETIRED_ELECTRON_OWNER_MISMATCH")
    scale = float(mp.get_parameter(actual, target, "coef") or "nan")
    if not math.isfinite(scale) or scale <= 0.0 or (mode == "physical" and scale != 1.0):
        raise code3.Code3ParityError("CURRENT_ELECTRON_SOURCE_SCALE_MISMATCH")
    if mode not in ("physical", "normalized"):
        raise code3.Code3ParityError("UNKNOWN_CURRENT_SOURCE_MODE")
    old = mp.upsert_parameter(actual, target, "type", code3.OLD)
    old = mp.remove_parameter(old, target, "v")
    old = mp.remove_parameter(old, target, "coef")
    old = mp.upsert_parameter(old, target, "number_source", functor)
    if mode == "physical":
        old = mp.upsert_parameter(old, target, "state_form", "physical")
    else:
        old = mp.upsert_parameter(old, target, "n_ref", format(1.0 / scale, ".17g"))
    if code3._outside_target(actual, target) != code3._outside_target(old, target):
        raise code3.Code3ParityError("VIRTUAL_LEGACY_NON_TARGET_DRIFT")
    return old


def pair(actual: str, target: str, functor: str, mode: str):
    original = virtual_legacy_from_current(actual, target, functor, mode)
    candidate, info = code3.replace_electron_only(original, path=target)
    if (mp.get_parameter(actual, target, "type") == code3.NEW and
        (mp.get_parameter(candidate, target, "v") != mp.get_parameter(actual, target, "v")
         or not math.isclose(float(mp.get_parameter(candidate, target, "coef") or "nan"),
                             float(mp.get_parameter(actual, target, "coef") or "nan"),
                             rel_tol=1e-15))):
        raise code3.Code3ParityError("VIRTUAL_REPLAY_DIFFERENT_FROM_LIVE_STANDARD")
    if code3._outside_target(original, target) != code3._outside_target(candidate, target):
        raise code3.Code3ParityError("NON_ELECTRON_BYTES_CHANGED")
    if info["source_functor"] != functor or info["mode"] != mode:
        raise code3.Code3ParityError("SOURCE_BINDING_CHANGED")
    if mode == "physical" and info["coefficient"] != 1.0:
        raise code3.Code3ParityError("PHYSICAL_COEFFICIENT_CHANGED")
    if mode == "normalized" and not (0.0 < info["coefficient"] < 1.0):
        raise code3.Code3ParityError("NORMALIZED_COEFFICIENT_CHANGED")
    # The old arm is virtual after Code3 retirement; only the actual standard
    # generator input is permitted in current-binary production CI.
    return original, actual if mp.get_parameter(actual, target, "type") == code3.NEW else candidate, info

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
