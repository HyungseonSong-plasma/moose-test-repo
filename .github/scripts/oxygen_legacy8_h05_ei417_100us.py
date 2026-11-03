#!/usr/bin/env python3
"""Controlled Legacy8 + H05 + EI-417 oxygen ICP experiment, research only.

One additional channel versus the H05 control:
    e + O2(X) -> O+(4S) + O(3P) + 2e
EI-417 mean-energy lookup comes ONLY from the existing private rate package.
17 eV/event is the existing provisional electron-energy loss. Science HOLD.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path

ROOT=Path("experiments/Issue395_powered_chemistry_ladder")
TABLE="EI-417_O2_X.txt"
TEN=["EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20","EI-2738","EI-407","H05","EI-417"]
ENERGY_LOSS_EV=17.0
CHECK_OLD="'$OELASTIC' ${O2A_EXTRA_INPUT} ${EI2738_EXTRA_INPUT}"
SOLVE_OLD="Outputs/file_base='$RESULT/run/plasma' ${O2A_EXTRA_INPUT} ${EI2738_EXTRA_INPUT}"
CHECK_NEW=CHECK_OLD+" '$EI407_OVERLAY' '$H05_OVERLAY' '$EI417_OVERLAY'"
SOLVE_NEW="${O2A_EXTRA_INPUT} ${EI2738_EXTRA_INPUT} '$EI407_OVERLAY' '$H05_OVERLAY' '$EI417_OVERLAY' Outputs/file_base='$RESULT/run/plasma'"

CONTENT="""# EI417 added to Legacy8+H05. e + O2(X) -> O+ + O(3P) + 2e.
# Private 100-point rate lookup, 17 eV electron energy loss per event.
# R_EI417 [mol/m3/s], one canonical progress owner; O2 remains constrained.
[FunctorMaterials]
  [legacy8_h05_ei417_o2_target]
    type = ADParsedFunctorMaterial
    property_name = c_O2_EI417
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w'
    expression = 'rho*w/0.032'
    block = plasma
  []
  [legacy8_h05_ei417_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = 'private_rates/EI-417_O2_X.txt'
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O2_EI417
    reaction_progress = R_EI417
    block = plasma
  []
  [legacy8_h05_ei417_electron_source]
    type = ADParsedFunctorMaterial
    property_name = S_e_molar_EI417
    functor_names = 'R_EI417'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [legacy8_h05_ei417_op_source]
    type = ADParsedFunctorMaterial
    property_name = S_Op_molar_EI417
    functor_names = 'R_EI417'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [legacy8_h05_ei417_o_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_EI417
    functor_names = 'R_EI417'
    functor_symbols = 'R'
    expression = '0.016*R'
    block = plasma
  []
  [legacy8_h05_ei417_constrained_o2_mass_sink]
    type = ADParsedFunctorMaterial
    property_name = S_O2_mass_EI417
    functor_names = 'R_EI417'
    functor_symbols = 'R'
    expression = '-0.032*R'
    block = plasma
  []
  [legacy8_h05_ei417_op_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_Op_mass_EI417
    functor_names = 'R_EI417'
    functor_symbols = 'R'
    expression = '0.016*R'
    block = plasma
  []
  [legacy8_h05_ei417_neutral_mass_sink]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_EI417
    functor_names = 'R_EI417'
    functor_symbols = 'R'
    expression = '-0.016*R'
    block = plasma
  []
  [legacy8_h05_ei417_energy_sink]
    type = ADParsedFunctorMaterial
    property_name = S_energy_EI417
    functor_names = 'R_EI417'
    functor_symbols = 'R'
    expression = '-17.0*R'
    block = plasma
  []
  [legacy8_h05_ei417_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_EI417
    functor_names = 'S_O2_mass_EI417 S_O_mass_EI417 S_Op_mass_EI417'
    functor_symbols = 'a b c'
    expression = 'a+b+c'
    block = plasma
  []
  [legacy8_h05_ei417_neutral_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_closure_EI417
    functor_names = 'S_O2_mass_EI417 S_O_mass_EI417 S_neutral_mass_EI417'
    functor_symbols = 'a b c'
    expression = 'a+b-c'
    block = plasma
  []
  [legacy8_h05_ei417_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_closure_EI417
    functor_names = 'S_e_molar_EI417 S_Op_molar_EI417'
    functor_symbols = 'el op'
    expression = 'op-el'
    block = plasma
  []
[]
[Kernels]
  [legacy8_h05_ei417_electron]
    type = FunctorKernel
    variable = log_ne
    functor = S_e_molar_EI417
    functor_on_rhs = true
    block = plasma
  []
  [legacy8_h05_ei417_electron_energy]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_EI417
    functor_on_rhs = true
    block = plasma
  []
[]
[FVKernels]
  [legacy8_h05_ei417_op]
    type = FVCoupledForce
    variable = log_nop
    v = S_Op_molar_EI417
    coef = 1.0
    block = plasma
  []
  [legacy8_h05_ei417_atomic_o]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_EI417
    block = plasma
  []
  [legacy8_h05_ei417_fluid_mass]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_EI417
    coef = 1.0
    block = plasma
  []
[]
[Postprocessors]
  [legacy8_h05_ei417_rate_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_EI417
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [legacy8_h05_ei417_electron_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_e_molar_EI417
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [legacy8_h05_ei417_energy_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_energy_EI417
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [legacy8_h05_ei417_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_EI417
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [legacy8_h05_ei417_neutral_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_neutral_mass_closure_EI417
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [legacy8_h05_ei417_charge_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_closure_EI417
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""

def h05():
    path=Path(os.environ.get("H05","_legacy6_control/.github/scripts/oxygen_legacy8_h05_100us.py"))
    spec=importlib.util.spec_from_file_location("control_h05_ei417",path)
    if spec is None or spec.loader is None:
        raise ValueError("H05 harness missing")
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def overlay(power):
    return ROOT/f"ei417_dissociative_ionization_{power}w_100us_dt1000ns_overlay.i"

def private_table():
    return ROOT/"private_rates"/TABLE

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def overlay_ok(source):
    tokens=(
        "reaction_progress = R_EI417",
        "rate_table_file = 'private_rates/EI-417_O2_X.txt'",
        "target_molar_concentration = c_O2_EI417",
        "functor = S_e_molar_EI417",
        "functor = S_energy_EI417",
        "variable = log_ne",
        "variable = log_energy",
        "variable = log_nop",
        "variable = w_O",
        "variable = p",
        "expression = '-17.0*R'",
        "expression = '-0.032*R'",
        "expression = '0.016*R'",
        "expression = '-0.016*R'",
        "expression = 'a+b+c'",
        "expression = 'a+b-c'",
        "expression = 'op-el'",
    )
    if any(token not in source for token in tokens):
        raise ValueError("EI417 overlay missing source/closure")
    if source.count("reaction_progress = R_EI417") != 1:
        raise ValueError("duplicate EI417 kinetic owner")
    if source.count("functor_on_rhs = true") != 2:
        raise ValueError("wrong EI417 electron/energy source ownership")
    if "variable = w_O2" in source or "R_EI415" in source or "functor_symbols = 'e " in source:
        raise ValueError("unwanted independent chemistry source or reserved symbol")
    return True

def verify(power):
    parent=h05()
    l8=parent.load_legacy8()
    l7=l8.l7()
    m=l7.legacy6()
    if (os.environ.get("OXYGEN_RESEARCH_EI2738_FORMULA")!="1" or
        os.environ.get("OXYGEN_RESEARCH_FULL24")!="0" or
        os.environ.get("OXYGEN_RESEARCH_LUMPED_O2A")!="0"):
        raise ValueError("Legacy8+H05+EI417 environment mismatch")
    m.check_input(power)
    l7.validate_overlay(l7.overlay_path(m,power).read_text())
    l8.overlay_ok(l8.overlay(power).read_text())
    parent.overlay_ok(parent.overlay(power).read_text())
    parent.reference_ok()
    ref_sha=digest(parent.REF)
    l8.table_ok(l8.rate())
    rate_sha=l8.table_ok(private_table())
    overlay_ok(overlay(power).read_text())
    path=m.result(power)/"legacy6_latest_variant.json"
    manifest=json.loads(path.read_text())
    if (manifest.get("variant")!="LEGACY8_H05_EI417_from_Legacy8_H05" or
        manifest.get("chemistry_channels")!=TEN or
        manifest.get("h05_reference_sha256")!=ref_sha or
        manifest.get("h05_rate_particle_m3_s")!=parent.A_PARTICLE or
        manifest.get("h05_electron_energy_source")!="none_unresolved" or
        manifest.get("ei407_lookup_sha256")!=digest(l8.rate()) or
        manifest.get("ei417_lookup_sha256")!=rate_sha or
        manifest.get("ei417_energy_loss_eV")!=ENERGY_LOSS_EV or
        manifest.get("scientific_acceptance")!="HOLD" or
        manifest.get("native_initialization")!="fresh_not_restarted" or
        manifest.get("physics_source_sha")!=m.RECIPE_SHA):
        raise ValueError("Legacy8+H05+EI417 provenance mismatch")
    print("LEGACY8_H05_EI417_P0_PASS",power,rate_sha)
    return parent,l8,l7,m,manifest

def prepare(power):
    parent=h05()
    parent.prepare(power)
    l8=parent.load_legacy8()
    src=Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/TABLE
    rate_sha=l8.table_ok(src)
    dest=private_table()
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and digest(dest)!=rate_sha:
        raise ValueError("private EI417 rate conflict")
    shutil.copyfile(src,dest)
    target=overlay(power)
    if target.exists():
        raise ValueError("refuse EI417 overlay overwrite")
    overlay_ok(CONTENT)
    target.write_text(CONTENT)
    l7=l8.l7()
    m=l7.legacy6()
    record=m.result(power)/"legacy6_latest_variant.json"
    data=json.loads(record.read_text())
    if data.get("chemistry_channels")!=TEN[:-1]:
        raise ValueError("not exactly nine H05 control channels")
    data.update({
        "variant":"LEGACY8_H05_EI417_from_Legacy8_H05",
        "chemistry_channels":TEN,
        "ei417_reaction":"e + O2(X) -> O+ + O + 2e",
        "ei417_lookup_filename":TABLE,
        "ei417_lookup_sha256":rate_sha,
        "ei417_energy_loss_eV":ENERGY_LOSS_EV,
        "ei417_lookup_origin":"Oxygen25 private HPEM rate package; science HOLD",
        "h05_reference_only_parent":"Legacy8 + H05, unchanged",
        "scientific_acceptance":"HOLD"
    })
    record.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    verify(power)
    print("LEGACY8_H05_EI417_PREPARED",power)

def patch(power):
    parent,l8,l7,m,data=verify(power)
    path=m.CHEM/"issue397_l1_power_scan_replay.sh"
    src=path.read_text()
    if (src.count(CHECK_OLD)!=1 or src.count(SOLVE_OLD)!=1 or
        "$H05_OVERLAY" in src or "$EI417_OVERLAY" in src):
        raise ValueError("unexpected replay control; refuse EI417 argv patch")
    dst=src.replace(CHECK_OLD,CHECK_NEW,1).replace(SOLVE_OLD,SOLVE_NEW,1)
    if dst.count(CHECK_NEW)!=1 or dst.count(SOLVE_NEW)!=1:
        raise ValueError("EI417 argv patch failed")
    path.write_text(dst)
    (m.result(power)/"legacy8_h05_ei417_argv_patch.json").write_text(json.dumps({
        "power_W":power,
        "original_sha256":hashlib.sha256(src.encode()).hexdigest(),
        "new_sha256":hashlib.sha256(dst.encode()).hexdigest(),
        "inputs":["EI-2738","EI-407","H05","EI-417"],
        "scientific_acceptance":"HOLD"
    },indent=2)+"\n")
    print("LEGACY8_H05_EI417_ARGV_PASS",power)

def archive(power):
    parent,l8,l7,m,data=verify(power)
    m.PERSIST=tuple(m.PERSIST)+(l7.overlay_path(m,power).name,
        l8.overlay(power).name,parent.overlay(power).name,overlay(power).name)
    m.verify_and_archive(power)
    path=m.result(power)/"legacy6_restart_100000ns_manifest.json"
    saved=json.loads(path.read_text())
    if (saved["native_endpoint_s"]!=1e-4 or
        not saved["verified_full_native_100us_checkpoint"] or
        saved["chemistry_channels"]!=TEN or
        saved["scientific_acceptance"]!="HOLD"):
        raise ValueError("EI417 100us native endpoint not verified")
    inventory=[p["path"] for p in saved["inventory"]["inputs"]]
    for target in (l7.overlay_path(m,power),l8.overlay(power),
                   parent.overlay(power),overlay(power)):
        if not any(p.endswith("/"+target.name) for p in inventory):
            raise ValueError("missing required chemistry overlay in archive")
    if any("private_rates" in p for p in inventory):
        raise ValueError("private rate leaked to archive")
    saved.update({
        "restart_requires_exact_legacy6_chemistry":False,
        "restart_requires_exact_legacy8_h05_ei417_chemistry":True,
        "ei407_recovery_private_rate_required":l8.RATE,
        "ei407_recovery_rate_sha256":data["ei407_lookup_sha256"],
        "ei417_recovery_private_rate_required":TABLE,
        "ei417_recovery_rate_sha256":data["ei417_lookup_sha256"],
        "h05_energy_incomplete":True,
    })
    path.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("LEGACY8_H05_EI417_NATIVE_100US_PASS",power,saved["actual_moose_step"])

def self_test():
    overlay_ok(CONTENT)
    assert len(TEN)==10 and TEN[-2:]==["H05","EI-417"]
    assert abs((-0.032+0.016+0.016))<1e-15
    assert abs((-0.032+0.016)-(-0.016))<1e-15
    assert abs((1)-(1))<1e-15
    for bad in (CONTENT.replace("reaction_progress = R_EI417","reaction_progress = R_BAD"),
                CONTENT.replace("variable = log_nop","variable = log_ni"),
                CONTENT.replace("expression = 'op-el'","expression = 'op+el'")):
        try:overlay_ok(bad)
        except ValueError:pass
        else:raise AssertionError("negative EI417 mutation not caught")
    print("LEGACY8_H05_EI417_SELFTEST_PASS")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    for flag in ("self-test","prepare-variant","verify-ten","patch-replay-argv","verify-and-archive"):
        g.add_argument("--"+flag,action="store_true")
    p.add_argument("--power-w",type=int,choices=(400,1000))
    a=p.parse_args()
    if a.self_test:self_test()
    elif a.power_w is None:p.error("--power-w required")
    elif a.prepare_variant:prepare(a.power_w)
    elif a.verify_ten:verify(a.power_w)
    elif a.patch_replay_argv:patch(a.power_w)
    else:archive(a.power_w)
