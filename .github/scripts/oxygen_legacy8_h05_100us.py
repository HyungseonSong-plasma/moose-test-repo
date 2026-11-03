#!/usr/bin/env python3
"""Legacy8 + H05 associative detachment: O- + O -> O2 + e; native 0-100us.
A = 3.0e-16 m3/s (particle basis), temperature exponent zero.
H05 electron birth energy is unassigned; research-only SCIENCE_HOLD.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path

ROOT = Path("experiments/Issue395_powered_chemistry_ladder")
A_PARTICLE = 3.0e-16
AVOGADRO = 6.02214076e23
H05_ID = "H05"
REF = Path("physics_app/data/heavy_reactions/stage5_s5e_h05_oxygen_heavy.txt")
EXPECTED_REF = (
    "reaction H05_Om_O_to_O2_electron volume power_law",
    "reactant Om 1",
    "reactant O 1",
    "product O2 1",
    "product electron 1",
    "A 3e-16",
    "basis particle",
    "T_ref 300",
    "exponent 0",
)

OVERLAY = """# Legacy8 + H05: O- + O -> O2 + e (associative detachment)
# k=3e-16 m3/s, temperature independent; one shared molar progress owner.
# c_Om = exp(log_nm) mol/m3; c_O = rho_neutral*w_O/0.016 mol/m3.
# R [mol/(m3 s)] = k[m3/s] * N_A[1/mol] * c_Om * c_O.
# O2(X) is a constrained residual species: no separate O2 source kernel.
# Electron energy convention from historical Stage-5 S5-E: no explicit H05
# electron-energy source; its physical uncertainty remains SCIENCE_HOLD.
[FunctorMaterials]
  [legacy8_h05_negative_ion_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_Om_H05
    functor_names = 'log_nm'
    functor_symbols = 'lnc'
    expression = 'exp(lnc)'
    block = plasma
  []
  [legacy8_h05_neutral_atomic_oxygen_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O_H05
    functor_names = 'rho_neutral w_O'
    functor_symbols = 'rho w'
    expression = 'rho*w/0.016'
    block = plasma
  []
  [legacy8_h05_progress]
    type = ADParsedFunctorMaterial
    property_name = R_H05
    functor_names = 'c_Om_H05 c_O_H05'
    functor_symbols = 'a b'
    expression = '3.0e-16*6.02214076e23*a*b'
    block = plasma
  []
  [legacy8_h05_electron_source]
    type = ADParsedFunctorMaterial
    property_name = S_e_molar_H05
    functor_names = 'R_H05'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [legacy8_h05_negative_ion_sink]
    type = ADParsedFunctorMaterial
    property_name = S_Om_molar_H05
    functor_names = 'R_H05'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [legacy8_h05_atomic_oxygen_sink]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_H05
    functor_names = 'R_H05'
    functor_symbols = 'R'
    expression = '-0.016*R'
    block = plasma
  []
  [legacy8_h05_negative_ion_mass_sink]
    type = ADParsedFunctorMaterial
    property_name = S_Om_mass_H05
    functor_names = 'R_H05'
    functor_symbols = 'R'
    expression = '-0.016*R'
    block = plasma
  []
  [legacy8_h05_constrained_o2_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O2_mass_H05
    functor_names = 'R_H05'
    functor_symbols = 'R'
    expression = '0.032*R'
    block = plasma
  []
  [legacy8_h05_neutral_fluid_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_H05
    functor_names = 'R_H05'
    functor_symbols = 'R'
    expression = '0.016*R'
    block = plasma
  []
  [legacy8_h05_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_H05
    functor_names = 'S_O2_mass_H05 S_O_mass_H05 S_Om_mass_H05'
    functor_symbols = 'a b c'
    expression = 'a+b+c'
    block = plasma
  []
  [legacy8_h05_neutral_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_closure_H05
    functor_names = 'S_O2_mass_H05 S_O_mass_H05 S_neutral_mass_H05'
    functor_symbols = 'a b c'
    expression = 'a+b-c'
    block = plasma
  []
  [legacy8_h05_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_closure_H05
    functor_names = 'S_e_molar_H05 S_Om_molar_H05'
    functor_symbols = 'e om'
    expression = 'e+om'
    block = plasma
  []
[]
[Kernels]
  [legacy8_h05_electron]
    type = FunctorKernel
    variable = log_ne
    functor = S_e_molar_H05
    functor_on_rhs = true
    block = plasma
  []
[]
[FVKernels]
  [legacy8_h05_negative_ion]
    type = FVCoupledForce
    variable = log_nm
    v = S_Om_molar_H05
    coef = 1.0
    block = plasma
  []
  [legacy8_h05_atomic_oxygen]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_H05
    block = plasma
  []
  [legacy8_h05_fluid_mass]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_H05
    coef = 1.0
    block = plasma
  []
[]
[Postprocessors]
  [legacy8_h05_rate_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_H05
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [legacy8_h05_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_H05
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [legacy8_h05_neutral_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_neutral_mass_closure_H05
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [legacy8_h05_charge_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_closure_H05
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""

def load_legacy8():
    p = Path(os.environ.get("LEGACY8", "_legacy6_control/.github/scripts/oxygen_legacy8_ei407_100us.py"))
    spec = importlib.util.spec_from_file_location("control_legacy8_h05", p)
    if spec is None or spec.loader is None:
        raise ValueError("Legacy8 harness missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def overlay(power):
    return ROOT / f"h05_associative_detachment_{power}w_100us_dt1000ns_overlay.i"

def reference_ok():
    src = REF.read_text()
    if any(src.count(token) != 1 for token in EXPECTED_REF):
        raise ValueError("H05 source kinetic/stoichiometric contract changed")
    return hashlib.sha256(REF.read_bytes()).hexdigest()

def overlay_ok(src):
    must = (
        "property_name = R_H05",
        "expression = '3.0e-16*6.02214076e23*a*b'",
        "functor_names = 'c_Om_H05 c_O_H05'",
        "functor = S_e_molar_H05",
        "variable = log_ne",
        "variable = log_nm",
        "variable = w_O",
        "variable = p",
        "expression = 'a+b+c'",
        "expression = 'a+b-c'",
        "expression = 'e+om'",
    )
    if any(s not in src for s in must):
        raise ValueError("H05 overlay missing source/closure")
    if src.count("property_name = R_H05") != 1:
        raise ValueError("duplicate H05 progress owner")
    if src.count("functor_on_rhs = true") != 1:
        raise ValueError("duplicate electron projector")
    if "variable = log_energy" in src or "variable = w_O2" in src:
        raise ValueError("H05 must not add unverified energy or second O2 owner")
    return True

def verify(power):
    l8 = load_legacy8()
    l7 = l8.l7()
    m = l7.legacy6()
    if os.environ.get("OXYGEN_RESEARCH_EI2738_FORMULA") != "1" or os.environ.get("OXYGEN_RESEARCH_FULL24") != "0" or os.environ.get("OXYGEN_RESEARCH_LUMPED_O2A") != "0":
        raise ValueError("Legacy8 flags incompatible")
    m.check_input(power)
    l7.validate_overlay(l7.overlay_path(m, power).read_text())
    l8.overlay_ok(l8.overlay(power).read_text())
    lookup_sha = l8.table_ok(l8.rate())
    overlay_ok(overlay(power).read_text())
    reference_sha = reference_ok()
    record = m.result(power) / "legacy6_latest_variant.json"
    manifest = json.loads(record.read_text())
    if (manifest.get("variant") != "LEGACY8_PLUS_H05_from_Legacy8" or
        manifest.get("chemistry_channels") != l8.EIGHT + [H05_ID] or
        manifest.get("ei407_lookup_sha256") != lookup_sha or
        manifest.get("h05_reference_sha256") != reference_sha or
        manifest.get("h05_rate_particle_m3_s") != A_PARTICLE or
        manifest.get("h05_electron_energy_source") != "none_unresolved" or
        manifest.get("scientific_acceptance") != "HOLD" or
        manifest.get("native_initialization") != "fresh_not_restarted" or
        manifest.get("physics_source_sha") != m.RECIPE_SHA):
        raise ValueError("Legacy8+H05 provenance mismatch")
    print("LEGACY8_H05_P0_PASS", power, reference_sha)
    return l8, l7, m, manifest

def prepare(power):
    l8 = load_legacy8()
    l8.prepare(power)
    ref_sha = reference_ok()
    path = overlay(power)
    if path.exists():
        raise ValueError("refuse H05 overlay overwrite")
    overlay_ok(OVERLAY)
    path.write_text(OVERLAY)
    l7 = l8.l7()
    m = l7.legacy6()
    record = m.result(power) / "legacy6_latest_variant.json"
    data = json.loads(record.read_text())
    if data["chemistry_channels"] != l8.EIGHT:
        raise ValueError("Legacy8 control channels mismatch")
    data.update({
        "variant": "LEGACY8_PLUS_H05_from_Legacy8",
        "chemistry_channels": l8.EIGHT + [H05_ID],
        "rate_origin": "Legacy8 plus historical H05 constant associative detachment",
        "h05_reaction": "O- + O -> O2 + e",
        "h05_rate_particle_m3_s": A_PARTICLE,
        "h05_temperature_exponent": 0,
        "h05_reference_file": REF.as_posix(),
        "h05_reference_sha256": ref_sha,
        "h05_electron_energy_source": "none_unresolved",
        "h05_added_only": True,
        "scientific_acceptance": "HOLD",
    })
    record.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    verify(power)
    print("LEGACY8_H05_PREPARED", power)

def patch(power):
    l8, l7, m, manifest = verify(power)
    path = m.CHEM / "issue397_l1_power_scan_replay.sh"
    src = path.read_text()
    check = l8.CHECK_NEW + " '$H05_OVERLAY'"
    solve = l8.SOLVE_NEW.replace(" Outputs/file_base=", " '$H05_OVERLAY' Outputs/file_base=")
    if (src.count(l8.CHECK_OLD) != 1 or src.count(l8.SOLVE_OLD) != 1 or
        check in src or solve in src or "$H05_OVERLAY" in src):
        raise ValueError("pinned replay argv differs; refuse unsafe H05 injection")
    dst = src.replace(l8.CHECK_OLD, check, 1).replace(l8.SOLVE_OLD, solve, 1)
    if dst.count(check) != 1 or dst.count(solve) != 1:
        raise ValueError("H05 argv injection failed")
    path.write_text(dst)
    (m.result(power) / "legacy8_h05_argv_patch.json").write_text(json.dumps({
        "power_W": power, "original_sha256": hashlib.sha256(src.encode()).hexdigest(),
        "new_sha256": hashlib.sha256(dst.encode()).hexdigest(),
        "source_inputs_extra": ["EI-2738", "EI-407", "H05"],
        "scientific_acceptance": "HOLD"
    }, indent=2) + "\n")
    print("LEGACY8_H05_ARGV_PASS", power)

def archive(power):
    l8, l7, m, record = verify(power)
    m.PERSIST = tuple(m.PERSIST) + (l7.overlay_path(m, power).name,
                l8.overlay(power).name, overlay(power).name)
    m.verify_and_archive(power)
    path = m.result(power) / "legacy6_restart_100000ns_manifest.json"
    saved = json.loads(path.read_text())
    if (saved["native_endpoint_s"] != 1e-4 or
        not saved["verified_full_native_100us_checkpoint"] or
        saved["chemistry_channels"] != l8.EIGHT + [H05_ID] or
        saved["scientific_acceptance"] != "HOLD"):
        raise ValueError("H05 final state/provenance is not valid")
    names = [p["path"] for p in saved["inventory"]["inputs"]]
    for target in (l7.overlay_path(m,power), l8.overlay(power),overlay(power)):
        if not any(n.endswith("/" + target.name) for n in names):
            raise ValueError("missing chemistry overlay in final archive")
    if any("private_rates" in n for n in names):
        raise ValueError("private lookup leaked to artifact")
    saved.update({
        "restart_requires_exact_legacy6_chemistry": False,
        "restart_requires_exact_legacy8_h05_chemistry": True,
        "ei407_recovery_private_rate_required": l8.RATE,
        "ei407_recovery_rate_sha256": record["ei407_lookup_sha256"],
        "h05_reference_sha256": record["h05_reference_sha256"],
        "h05_kinetics_particle_m3_s": A_PARTICLE,
        "h05_energy_incomplete": True,
    })
    path.write_text(json.dumps(saved, indent=2, sort_keys=True) + "\n")
    print("LEGACY8_H05_NATIVE_100US_PASS", power, saved["actual_moose_step"])

def self_test():
    overlay_ok(OVERLAY)
    assert A_PARTICLE * AVOGADRO == 180664222.8
    assert math.isclose(0.032 - 0.016 - 0.016, 0, abs_tol=1e-15)
    assert math.isclose(0.032 - 0.016 - 0.016, 0, abs_tol=1e-15)
    for corrupted in (OVERLAY.replace("property_name = R_H05", "property_name = R_WRONG"),
                      OVERLAY.replace("variable = log_nm", "variable = log_ni"),
                      OVERLAY + "\nvariable = log_energy\n"):
        try: overlay_ok(corrupted)
        except ValueError: pass
        else: raise AssertionError("negative H05 self-test missed invalid overlay")
    print("LEGACY8_H05_SELFTEST_PASS")

def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    for name in ("self-test","prepare-variant","verify-nine",
                 "patch-replay-argv","verify-and-archive"):
        g.add_argument("--" + name, action="store_true")
    p.add_argument("--power-w", type=int, choices=(400,1000))
    a = p.parse_args()
    if a.self_test:
        self_test()
    elif a.power_w is None:
        p.error("--power-w required")
    elif a.prepare_variant:
        prepare(a.power_w)
    elif a.verify_nine:
        verify(a.power_w)
    elif a.patch_replay_argv:
        patch(a.power_w)
    elif a.verify_and_archive:
        archive(a.power_w)

if __name__ == "__main__":
    main()
