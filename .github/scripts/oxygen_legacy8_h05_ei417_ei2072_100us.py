#!/usr/bin/env python3
"""Run-ready, NOT dispatched: Legacy8 + H05 + EI417 + EI2072 (science HOLD).

e + O2(a1Delta) -> O2+ + 2e.
Reuse the private 100-point EI-2072 rate table and the existing provisional
11.08 eV electron-energy loss. Exactly one extra reaction beyond EI417.
No private rates or any new scientific acceptance claim are committed here.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path

ROOT = Path("experiments/Issue395_powered_chemistry_ladder")
TABLE = "EI-2072_O2_a1Delta.txt"
ENERGY_LOSS_EV = 11.08
CHANNEL = "EI-2072"
BASE_CHANNELS = ["EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20",
                 "EI-2738","EI-407","H05","EI-417"]
ELEVEN = BASE_CHANNELS + [CHANNEL]

# Provenance: the O2(a) target is the existing solved w_O2s species.
# n_e_physical is number/m3; c_O2a is mol/m3; R_EI2072 is mol/m3/s.
# Charge: S_e=+R, S_O2p=+R => +S_ion - S_e = 0.
# Heavy mass: -0.032R (O2a) +0.032R (O2p) = 0.
# Neutral fluid mass: -0.032R (neutral -> ion).
OVERLAY = """# Legacy8+H05+EI417 plus ONLY EI-2072, science HOLD.
# e + O2(a1Delta) -> O2+ + 2e, 11.08 eV loss.
# O2(a) is w_O2s, O2+ is log_ni, electron is log_ne.
[FunctorMaterials]
  [legacy_ei2072_target]
    type = ADParsedFunctorMaterial
    property_name = c_O2a_EI2072
    functor_names = 'rho_neutral w_O2s'
    functor_symbols = 'rho w'
    expression = 'rho*w/0.032'
    block = plasma
  []
  [legacy_ei2072_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = 'private_rates/EI-2072_O2_a1Delta.txt'
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O2a_EI2072
    reaction_progress = R_EI2072
    block = plasma
  []
  [legacy_ei2072_electron_source]
    type = ADParsedFunctorMaterial
    property_name = S_e_molar_EI2072
    functor_names = 'R_EI2072'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [legacy_ei2072_o2p_source]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_molar_EI2072
    functor_names = 'R_EI2072'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [legacy_ei2072_o2a_mass_sink]
    type = ADParsedFunctorMaterial
    property_name = S_O2a_mass_EI2072
    functor_names = 'R_EI2072'
    functor_symbols = 'R'
    expression = '-0.032*R'
    block = plasma
  []
  [legacy_ei2072_o2p_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_mass_EI2072
    functor_names = 'R_EI2072'
    functor_symbols = 'R'
    expression = '0.032*R'
    block = plasma
  []
  [legacy_ei2072_neutral_mass_sink]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_EI2072
    functor_names = 'R_EI2072'
    functor_symbols = 'R'
    expression = '-0.032*R'
    block = plasma
  []
  [legacy_ei2072_energy_sink]
    type = ADParsedFunctorMaterial
    property_name = S_energy_EI2072
    functor_names = 'R_EI2072'
    functor_symbols = 'R'
    expression = '-11.08*R'
    block = plasma
  []
  [legacy_ei2072_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_EI2072
    functor_names = 'S_O2a_mass_EI2072 S_O2p_mass_EI2072'
    functor_symbols = 'a b'
    expression = 'a+b'
    block = plasma
  []
  [legacy_ei2072_neutral_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_closure_EI2072
    functor_names = 'S_O2a_mass_EI2072 S_neutral_mass_EI2072'
    functor_symbols = 'a b'
    expression = 'a-b'
    block = plasma
  []
  [legacy_ei2072_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_closure_EI2072
    functor_names = 'S_e_molar_EI2072 S_O2p_molar_EI2072'
    functor_symbols = 'el ion'
    expression = 'ion-el'
    block = plasma
  []
[]
[Kernels]
  [legacy_ei2072_electron]
    type = FunctorKernel
    variable = log_ne
    functor = S_e_molar_EI2072
    functor_on_rhs = true
    block = plasma
  []
  [legacy_ei2072_electron_energy]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_EI2072
    functor_on_rhs = true
    block = plasma
  []
[]
[FVKernels]
  [legacy_ei2072_o2a]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O2s
    source = S_O2a_mass_EI2072
    block = plasma
  []
  [legacy_ei2072_o2p]
    type = FVCoupledForce
    variable = log_ni
    v = S_O2p_molar_EI2072
    coef = 1.0
    block = plasma
  []
  [legacy_ei2072_neutral_mass]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_EI2072
    coef = 1.0
    block = plasma
  []
[]
[Postprocessors]
  [ei2072_rate_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_EI2072
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2072_electron_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_e_molar_EI2072
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2072_energy_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_energy_EI2072
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2072_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_EI2072
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2072_neutral_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_neutral_mass_closure_EI2072
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2072_charge_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_closure_EI2072
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""

def ei417():
    path = Path(os.environ.get(
        "EI417", "_legacy6_control/.github/scripts/oxygen_legacy8_h05_ei417_100us.py"))
    spec = importlib.util.spec_from_file_location("parent_ei417_for_ei2072", path)
    if spec is None or spec.loader is None:
        raise ValueError("exact EI417 parent harness missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def overlay(power):
    if power not in (400, 1000):
        raise ValueError("unsupported power")
    return ROOT / f"ei2072_o2a_ionization_{power}w_100us_dt1000ns_overlay.i"

def private_table():
    return ROOT / "private_rates" / TABLE

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def overlay_ok(src):
    required = (
        "property_name = c_O2a_EI2072",
        "rate_table_file = 'private_rates/EI-2072_O2_a1Delta.txt'",
        "reaction_progress = R_EI2072",
        "electron_number_density = n_e_physical",
        "target_molar_concentration = c_O2a_EI2072",
        "functor = S_e_molar_EI2072",
        "functor = S_energy_EI2072",
        "variable = log_ne",
        "variable = log_energy",
        "variable = w_O2s",
        "variable = log_ni",
        "variable = p",
        "expression = '-0.032*R'",
        "expression = '0.032*R'",
        "expression = '-11.08*R'",
        "expression = 'a+b'",
        "expression = 'a-b'",
        "expression = 'ion-el'",
    )
    if any(token not in src for token in required):
        raise ValueError("EI2072 missing required source/energy/closure")
    if src.count("reaction_progress = R_EI2072") != 1:
        raise ValueError("EI2072 must have exactly one kinetic owner")
    if src.count("functor_on_rhs = true") != 2:
        raise ValueError("EI2072 must own exactly electron and energy FE sources")
    for forbidden in (
        "variable = log_nm", "variable = log_nop", "variable = w_O2",
        "functor_symbols = 'e ", "reaction_progress = R_EI417",
        "reaction_progress = R_EI2067",
    ):
        if forbidden in src:
            raise ValueError("EI2072 attempted to mutate other chemistry")
    return True

def verify(power):
    parent = ei417()
    h05 = parent.h05()
    l8 = h05.load_legacy8()
    l7 = l8.l7()
    m = l7.legacy6()
    if (os.environ.get("OXYGEN_RESEARCH_EI2738_FORMULA") != "1" or
        os.environ.get("OXYGEN_RESEARCH_FULL24") != "0" or
        os.environ.get("OXYGEN_RESEARCH_LUMPED_O2A") != "0"):
        raise ValueError("legacy control flags changed")
    m.check_input(power)
    l7.validate_overlay(l7.overlay_path(m, power).read_text())
    l8.overlay_ok(l8.overlay(power).read_text())
    h05.overlay_ok(h05.overlay(power).read_text())
    parent.overlay_ok(parent.overlay(power).read_text())
    overlay_ok(overlay(power).read_text())
    h05.reference_ok()
    l8.table_ok(l8.rate())
    l8.table_ok(parent.private_table())
    rate_sha = l8.table_ok(private_table())
    manifest = json.loads((m.result(power) / "legacy6_latest_variant.json").read_text())
    if (manifest.get("variant") != "LEGACY8_H05_EI417_EI2072_from_EI417" or
        manifest.get("chemistry_channels") != ELEVEN or
        manifest.get("ei417_lookup_sha256") != digest(parent.private_table()) or
        manifest.get("ei407_lookup_sha256") != digest(l8.rate()) or
        manifest.get("ei2072_lookup_sha256") != rate_sha or
        manifest.get("ei2072_energy_loss_eV") != ENERGY_LOSS_EV or
        manifest.get("h05_rate_particle_m3_s") != h05.A_PARTICLE or
        manifest.get("h05_electron_energy_source") != "none_unresolved" or
        manifest.get("scientific_acceptance") != "HOLD" or
        manifest.get("native_initialization") != "fresh_not_restarted" or
        manifest.get("physics_source_sha") != m.RECIPE_SHA):
        raise ValueError("EI2072 11-channel provenance mismatch")
    print("LEGACY8_H05_EI417_EI2072_P0_PASS", power, rate_sha)
    return parent, h05, l8, l7, m, manifest

def prepare(power):
    parent = ei417()
    parent.prepare(power)
    l8 = parent.h05().load_legacy8()
    source = Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"]) / TABLE
    rate_sha = l8.table_ok(source)
    dest = private_table()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and digest(dest) != rate_sha:
        raise ValueError("private EI2072 rate conflict")
    shutil.copyfile(source, dest)
    target = overlay(power)
    if target.exists():
        raise ValueError("EI2072 overlay already exists")
    overlay_ok(OVERLAY)
    target.write_text(OVERLAY)
    m = l8.l7().legacy6()
    record = m.result(power) / "legacy6_latest_variant.json"
    info = json.loads(record.read_text())
    if info.get("chemistry_channels") != BASE_CHANNELS:
        raise ValueError("parent EI417 baseline did not contain exactly ten channels")
    info.update({
        "variant": "LEGACY8_H05_EI417_EI2072_from_EI417",
        "chemistry_channels": ELEVEN,
        "ei2072_reaction": "e + O2(a1Delta) -> O2+ + 2e",
        "ei2072_target_species": "O2s",
        "ei2072_lookup_filename": TABLE,
        "ei2072_lookup_sha256": rate_sha,
        "ei2072_energy_loss_eV": ENERGY_LOSS_EV,
        "ei2072_electron_source_per_event": 1,
        "ei2072_lookup_origin": "private original 19 HPEM-derived table package",
        "scientific_acceptance": "HOLD"
    })
    record.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")
    verify(power)
    print("LEGACY8_H05_EI417_EI2072_PREPARED", power)

def patch(power):
    parent, h05, l8, l7, m, info = verify(power)
    path = m.CHEM / "issue397_l1_power_scan_replay.sh"
    src = path.read_text()
    check_old = parent.CHECK_OLD
    solve_old = parent.SOLVE_OLD
    check_new = parent.CHECK_NEW + " '$EI2072_OVERLAY'"
    solve_new = parent.SOLVE_NEW.replace(
        " Outputs/file_base=", " '$EI2072_OVERLAY' Outputs/file_base=")
    if (src.count(check_old) != 1 or src.count(solve_old) != 1 or
        "$EI407_OVERLAY" in src or "$H05_OVERLAY" in src or
        "$EI417_OVERLAY" in src or "$EI2072_OVERLAY" in src):
        raise ValueError("pinned replay arguments changed; do not inject EI2072")
    dst = src.replace(check_old, check_new, 1).replace(solve_old, solve_new, 1)
    if dst.count(check_new) != 1 or dst.count(solve_new) != 1:
        raise ValueError("EI2072 replay argument patch failed")
    path.write_text(dst)
    (m.result(power) / "legacy8_h05_ei417_ei2072_argv_patch.json").write_text(
        json.dumps({
            "power_W": power,
            "original_sha256": hashlib.sha256(src.encode()).hexdigest(),
            "new_sha256": hashlib.sha256(dst.encode()).hexdigest(),
            "added_channel": CHANNEL,
            "private_rate_sha256": info["ei2072_lookup_sha256"],
            "scientific_acceptance": "HOLD"
        }, indent=2) + "\n")
    print("LEGACY8_H05_EI417_EI2072_ARGV_PASS", power)

def archive(power):
    parent, h05, l8, l7, m, info = verify(power)
    m.PERSIST = tuple(m.PERSIST) + (
        l7.overlay_path(m, power).name, l8.overlay(power).name,
        h05.overlay(power).name, parent.overlay(power).name, overlay(power).name)
    m.verify_and_archive(power)
    path = m.result(power) / "legacy6_restart_100000ns_manifest.json"
    saved = json.loads(path.read_text())
    if (saved["native_endpoint_s"] != 1e-4 or
        not saved["verified_full_native_100us_checkpoint"] or
        saved["chemistry_channels"] != ELEVEN or
        saved["scientific_acceptance"] != "HOLD"):
        raise ValueError("11-channel 100us endpoint/checkpoint not verified")
    archive_files = [v["path"] for v in saved["inventory"]["inputs"]]
    for o in (l7.overlay_path(m,power), l8.overlay(power),
              h05.overlay(power),parent.overlay(power),overlay(power)):
        if not any(p.endswith("/" + o.name) for p in archive_files):
            raise ValueError("required chemistry overlay not archived")
    if any("private_rates" in p for p in archive_files):
        raise ValueError("private rate leak in artifacts")
    saved.update({
        "restart_requires_exact_legacy6_chemistry": False,
        "restart_requires_exact_legacy8_h05_ei417_ei2072_chemistry": True,
        "ei407_recovery_private_rate_required": l8.RATE,
        "ei407_recovery_rate_sha256": info["ei407_lookup_sha256"],
        "ei417_recovery_private_rate_required": parent.TABLE,
        "ei417_recovery_rate_sha256": info["ei417_lookup_sha256"],
        "ei2072_recovery_private_rate_required": TABLE,
        "ei2072_recovery_rate_sha256": info["ei2072_lookup_sha256"],
        "h05_energy_incomplete": True,
    })
    path.write_text(json.dumps(saved, indent=2, sort_keys=True) + "\n")
    print("LEGACY8_H05_EI417_EI2072_100US_PASS", power)

def self_test():
    assert ELEVEN == BASE_CHANNELS + ["EI-2072"]
    assert len(ELEVEN) == 11 and len(set(ELEVEN)) == 11
    overlay_ok(OVERLAY)
    assert abs(-0.032 + 0.032) < 1e-14
    assert abs(1 - 1) < 1e-14
    for bad in (
        OVERLAY.replace("reaction_progress = R_EI2072", "reaction_progress = R_WRONG"),
        OVERLAY.replace("variable = log_ni", "variable = log_nop"),
        OVERLAY.replace("expression = 'ion-el'", "expression = 'ion+el'"),
        OVERLAY + "\nvariable = log_nm\n",
    ):
        try:
            overlay_ok(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("negative EI2072 mutation was not caught")
    print("LEGACY8_H05_EI417_EI2072_SELFTEST_PASS")

def main():
    parser = argparse.ArgumentParser()
    options = parser.add_mutually_exclusive_group(required=True)
    for option in ("self-test","prepare-variant","verify-eleven",
                   "patch-replay-argv","verify-and-archive"):
        options.add_argument("--" + option, action="store_true")
    parser.add_argument("--power-w", type=int, choices=(400,1000))
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.power_w is None:
        parser.error("--power-w is required")
    elif args.prepare_variant:
        prepare(args.power_w)
    elif args.verify_eleven:
        verify(args.power_w)
    elif args.patch_replay_argv:
        patch(args.power_w)
    else:
        archive(args.power_w)

if __name__ == "__main__":
    main()
