#!/usr/bin/env python3
"""11-channel oxygen ICP: Legacy8 + EI417 + EI935 + EI2058, excluding HOLD three.

EI2058 e + O2(a) -> O- + O, energy loss 3.50 eV/event.
Fresh 400/1000W, 0-100us research-only; science acceptance HOLD.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path

CHEM=Path("experiments/Issue395_powered_chemistry_ladder")
EI2058_RATE="EI-2058_O2_a1Delta.txt"
ENERGY_LOSS=3.5
HOLD={"H05","EI-2072","EI-2074"}

CONTENT="""# EI2058: e + O2(a1Delta) -> O- + O(3P).
# Original private EI-2058 rate table. R_EI2058 [mol/(m3 s)] single owner.
# Electron: -R; O-: +R; O2(a): -R; O: +R; Te-energy: -3.5*R.
[FunctorMaterials]
  [ei2058_o2a_target]
    type = ADParsedFunctorMaterial
    property_name = c_O2a_EI2058
    functor_names = 'rho_neutral w_O2s'
    functor_symbols = 'rho w'
    expression = 'rho*w/0.032'
    block = plasma
  []
  [ei2058_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = 'private_rates/EI-2058_O2_a1Delta.txt'
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O2a_EI2058
    reaction_progress = R_EI2058
    block = plasma
  []
  [ei2058_electron_sink]
    type = ADParsedFunctorMaterial
    property_name = S_e_molar_EI2058
    functor_names = 'R_EI2058'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [ei2058_om_birth]
    type = ADParsedFunctorMaterial
    property_name = S_Om_molar_EI2058
    functor_names = 'R_EI2058'
    functor_symbols = 'R'
    expression = 'R'
    block = plasma
  []
  [ei2058_o2a_sink]
    type = ADParsedFunctorMaterial
    property_name = S_O2s_mass_EI2058
    functor_names = 'R_EI2058'
    functor_symbols = 'R'
    expression = '-0.032*R'
    block = plasma
  []
  [ei2058_atomic_o_birth]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_EI2058
    functor_names = 'R_EI2058'
    functor_symbols = 'R'
    expression = '0.016*R'
    block = plasma
  []
  [ei2058_fluid_mass]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_EI2058
    functor_names = 'R_EI2058'
    functor_symbols = 'R'
    expression = '-0.016*R'
    block = plasma
  []
  [ei2058_e_energy]
    type = ADParsedFunctorMaterial
    property_name = S_energy_EI2058
    functor_names = 'R_EI2058'
    functor_symbols = 'R'
    expression = '-3.5*R'
    block = plasma
  []
  [ei2058_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_mass_closure_EI2058
    functor_names = 'S_O2s_mass_EI2058 S_O_mass_EI2058 S_neutral_mass_EI2058'
    functor_symbols = 'a b c'
    expression = 'a+b-c'
    block = plasma
  []
  [ei2058_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_closure_EI2058
    functor_names = 'S_e_molar_EI2058 S_Om_molar_EI2058'
    functor_symbols = 'el om'
    expression = '-el-om'
    block = plasma
  []
[]
[FVKernels]
  [ei2058_negative_ion]
    type = FVCoupledForce
    variable = log_nm
    v = S_Om_molar_EI2058
    coef = 1.0
    block = plasma
  []
  [ei2058_excited_oxygen]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O2s
    source = S_O2s_mass_EI2058
    block = plasma
  []
  [ei2058_atomic_oxygen]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_EI2058
    block = plasma
  []
  [ei2058_neutral_pressure]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_EI2058
    coef = 1.0
    block = plasma
  []
[]
[Kernels]
  [ei2058_electron]
    type = FunctorKernel
    variable = log_ne
    functor = S_e_molar_EI2058
    functor_on_rhs = true
    block = plasma
  []
  [ei2058_electron_energy]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_EI2058
    functor_on_rhs = true
    block = plasma
  []
[]
[Postprocessors]
  [ei2058_progress_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_EI2058
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2058_charge_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_closure_EI2058
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2058_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_mass_closure_EI2058
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei2058_energy_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_energy_EI2058
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""

def load_parent():
    path=Path(os.environ.get("EI935_PARENT",
            "_legacy6_control/.github/scripts/oxygen_legacy8_ei417_ei935_no_hold_100us.py"))
    spec=importlib.util.spec_from_file_location("no_hold_ei935_parent",path)
    if not spec or not spec.loader:raise FileNotFoundError(path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def overlay(power):return CHEM/f"ei2058_o2a_attachment_{power}w_100us_dt1000ns_overlay.i"
def rate():return CHEM/"private_rates"/EI2058_RATE
def channels(parent):return parent.CHANNELS+["EI-2058"]

def validate(s):
    required=(
        "reaction_progress = R_EI2058",
        "rate_table_file = 'private_rates/EI-2058_O2_a1Delta.txt'",
        "target_molar_concentration = c_O2a_EI2058",
        "variable = log_ne","variable = log_nm","variable = w_O2s",
        "variable = w_O","variable = p","variable = log_energy",
        "functor = S_e_molar_EI2058","v = S_Om_molar_EI2058",
        "source = S_O2s_mass_EI2058","source = S_O_mass_EI2058",
        "expression = '-R'","expression = 'R'",
        "expression = '-0.032*R'","expression = '0.016*R'",
        "expression = '-0.016*R'","expression = '-3.5*R'",
        "expression = 'a+b-c'","expression = '-el-om'",
    )
    if any(x not in s for x in required):raise ValueError("EI2058 source incomplete")
    if s.count("reaction_progress = R_EI2058")!=1:
        raise ValueError("duplicate EI2058 progress")
    if s.count("functor_on_rhs = true")!=2:
        raise ValueError("must have one electron sink and one energy sink")
    if "functor_symbols = 'e " in s:
        raise ValueError("reserved parser symbol e")
    if any("R_"+f in s for f in ("EI2072","EI2074")) or "R_H05" in s:
        raise ValueError("a HOLD reaction leaked into EI2058 overlay")

def verify(power):
    p=load_parent()
    b=p.l8();l7=b.l7();m=l7.legacy6()
    if any(os.environ.get(k)!=v for k,v in (
        ("OXYGEN_RESEARCH_EI2738_FORMULA","1"),
        ("OXYGEN_RESEARCH_FULL24","0"),
        ("OXYGEN_RESEARCH_LUMPED_O2A","0"))):
        raise ValueError("unexpected research flags")
    m.check_input(power)
    l7.validate_overlay(l7.overlay_path(m,power).read_text())
    b.overlay_ok(b.overlay(power).read_text())
    if p.f417(power).read_text()!=p.c417():raise ValueError("EI417 provenance mismatch")
    p.validate_935(p.f935(power).read_text())
    validate(overlay(power).read_text())
    rates=[b.RATE,p.R417,p.R935,EI2058_RATE]
    shas={name:b.table_ok(CHEM/"private_rates"/name) for name in rates}
    j=json.loads((m.result(power)/"legacy6_latest_variant.json").read_text())
    if (j.get("chemistry_channels")!=channels(p) or
        HOLD.intersection(j.get("chemistry_channels", []))):
        raise ValueError("wrong 11-ch inventory or held chemistry")
    if any((
        j.get("variant")!="LEGACY8_EI417_EI935_EI2058_NO_HOLD",
        j.get("scientific_acceptance")!="HOLD",
        j.get("native_initialization")!="fresh_not_restarted",
        j.get("physics_source_sha")!="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab",
        j.get("ei2058_energy_loss_eV")!=ENERGY_LOSS,
        j.get("ei407_lookup_sha256")!=shas[b.RATE],
        j.get("ei417_lookup_sha256")!=shas[p.R417],
        j.get("ei935_lookup_sha256")!=shas[p.R935],
        j.get("ei2058_lookup_sha256")!=shas[EI2058_RATE],
    )):
        raise ValueError("EI2058 input provenance mismatch")
    print("NO_HOLD_EI2058_P0_PASS",power,j["ei2058_lookup_sha256"])
    return p,b,l7,m,j

def prepare(power):
    p=load_parent()
    p.prepare(power) # original 10-channel fresh preparation (never a cross-chemistry restart)
    b=p.l8()
    source=Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/EI2058_RATE
    check_sha=b.table_ok(source)
    dest=rate();dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and digest(dest)!=check_sha:
        raise ValueError("private EI2058 lookup SHA changed")
    shutil.copyfile(source,dest)
    dest_overlay=overlay(power)
    if dest_overlay.exists():raise ValueError("refuse EI2058 overwrite")
    validate(CONTENT)
    dest_overlay.write_text(CONTENT)
    l7=b.l7();m=l7.legacy6()
    path=m.result(power)/"legacy6_latest_variant.json"
    j=json.loads(path.read_text())
    if j.get("chemistry_channels")!=p.CHANNELS or HOLD.intersection(j["chemistry_channels"]):
        raise ValueError("parent 10-channel inventory unexpected")
    j.update({
        "variant":"LEGACY8_EI417_EI935_EI2058_NO_HOLD",
        "chemistry_channels":channels(p),
        "hold_excluded":sorted(HOLD),
        "ei2058_reaction":"e+O2(a)->O-+O",
        "ei2058_lookup_filename":EI2058_RATE,
        "ei2058_lookup_sha256":check_sha,
        "ei2058_energy_loss_eV":ENERGY_LOSS,
        "ei2058_source":"original 100-point Oxygen25 private lookup; research-only",
        "scientific_acceptance":"HOLD",
    })
    path.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    verify(power)
    print("NO_HOLD_EI2058_PREPARED",power)

def patch(power):
    p,b,l7,m,j=verify(power)
    path=m.CHEM/"issue397_l1_power_scan_replay.sh"
    old=path.read_text()
    check=p.OLD_CHECK
    solve=p.OLD_SOLVE
    chk_new=p.NEW_CHECK+" '$EI2058_OVERLAY'"
    solv_new=p.NEW_SOLVE.replace(" Outputs/file_base=",
                " '$EI2058_OVERLAY' Outputs/file_base=")
    if old.count(check)!=1 or old.count(solve)!=1:
        raise ValueError("replay command diverged")
    if any(x in old for x in (
        "$H05_OVERLAY","$EI2072_OVERLAY","$EI2074_OVERLAY",
        "$EI407_OVERLAY","$EI417_OVERLAY","$EI935_OVERLAY","$EI2058_OVERLAY"
    )):
        raise ValueError("prior chemistry patch found")
    new=old.replace(check,chk_new,1).replace(solve,solv_new,1)
    if new.count(chk_new)!=1 or new.count(solv_new)!=1:
        raise ValueError("EI2058 argv patch failed")
    path.write_text(new)
    (m.result(power)/"ei2058_nohold_argv_patch.json").write_text(
        json.dumps({
            "power_W":power,
            "source_sha256":hashlib.sha256(old.encode()).hexdigest(),
            "patched_sha256":hashlib.sha256(new.encode()).hexdigest(),
            "overlays":["EI-2738","EI-407","EI-417","EI-935","EI-2058"],
            "hold_excluded":sorted(HOLD),
            "scientific_acceptance":"HOLD"
        },indent=2)+"\n")
    print("NO_HOLD_EI2058_ARGV_PASS",power)

def archive(power):
    p,b,l7,m,j=verify(power)
    m.PERSIST=tuple(m.PERSIST)+(l7.overlay_path(m,power).name,
        b.overlay(power).name,p.f417(power).name,p.f935(power).name,
        overlay(power).name)
    m.verify_and_archive(power)
    path=m.result(power)/"legacy6_restart_100000ns_manifest.json"
    saved=json.loads(path.read_text())
    if any((
        not saved["verified_full_native_100us_checkpoint"],
        saved["native_endpoint_s"]!=1e-4,
        saved["chemistry_channels"]!=channels(p),
        saved["scientific_acceptance"]!="HOLD",
        HOLD.intersection(saved["chemistry_channels"]),
    )):
        raise ValueError("invalid 11-channel 100us endpoint")
    names=[x["path"] for x in saved["inventory"]["inputs"]]
    expected=[l7.overlay_path(m,power),b.overlay(power),
              p.f417(power),p.f935(power),overlay(power)]
    for o in expected:
        if not any(n.endswith("/"+o.name) for n in names):
            raise ValueError("missing archived overlay "+o.name)
    if any("private_rates" in n or
           any(tag in n.lower() for tag in ("h05_associative","ei2072_o2a","ei2074_o2a"))
           for n in names):
        raise ValueError("private or held chemistry leaked")
    saved.update({
        "restart_requires_exact_legacy8_ei417_ei935_ei2058_chemistry":True,
        "restart_requires_exact_legacy6_chemistry":False,
        "hold_excluded":sorted(HOLD),
    })
    for key,name in (("ei407",b.RATE),("ei417",p.R417),("ei935",p.R935),
                     ("ei2058",EI2058_RATE)):
        saved[key+"_recovery_private_rate_required"]=name
        saved[key+"_recovery_rate_sha256"]=j[key+"_lookup_sha256"]
    path.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("NO_HOLD_EI2058_NATIVE_100US_PASS",power)

def self_test():
    p=load_parent()
    p.self_test()
    assert len(channels(p))==11 and not HOLD.intersection(channels(p))
    assert abs(-0.032+0.016+0.016)<1e-15
    assert abs(-(-1)-1)<1e-15
    validate(CONTENT)
    for wrong in (
        CONTENT.replace("reaction_progress = R_EI2058","reaction_progress = R_BAD"),
        CONTENT.replace("variable = log_nm","variable = log_nop"),
        CONTENT.replace("expression = '-3.5*R'","expression = '3.5*R'"),
        CONTENT.replace("expression = '-el-om'","expression = 'el+om'")
    ):
        try:validate(wrong)
        except ValueError:pass
        else:raise AssertionError("EI2058 bad source not rejected")
    print("NO_HOLD_EI2058_SELFTEST_PASS")

if __name__=="__main__":
    a=argparse.ArgumentParser()
    g=a.add_mutually_exclusive_group(required=True)
    for key in ("self-test","prepare-variant","verify-eleven","patch-replay-argv",
                "verify-and-archive"):
        g.add_argument("--"+key,action="store_true")
    a.add_argument("--power-w",type=int,choices=[400,1000])
    args=a.parse_args()
    if args.self_test:self_test()
    elif args.power_w is None:a.error("--power-w required")
    elif args.prepare_variant:prepare(args.power_w)
    elif args.verify_eleven:verify(args.power_w)
    elif args.patch_replay_argv:patch(args.power_w)
    else:archive(args.power_w)
