#!/usr/bin/env python3
"""Legacy9 = Legacy8 + EI2067 O2(a1Delta) superelastic excitation inverse.
Research-only fresh 0-100us 400/1000W; private rate lookup; SCIENCE_HOLD.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, os, shutil
from pathlib import Path

ROOT=Path("experiments/Issue395_powered_chemistry_ladder")
RATE_NAME="EI-2067_O2_a1Delta.txt"
BASE_SHA="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
NINE=["EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20","EI-2738","EI-407","EI-2067"]
def legacy8():
    path=Path(os.environ.get("LEGACY8","_legacy8_control/.github/scripts/oxygen_legacy8_ei407_100us.py"))
    spec=importlib.util.spec_from_file_location("legacy8_control",path)
    if spec is None or spec.loader is None: raise RuntimeError("Legacy8 source unavailable")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def rate(): return ROOT/"private_rates"/RATE_NAME
def overlay(power):
    if power not in (400,1000): raise ValueError("power must be 400 or 1000")
    return ROOT/f"ei2067_only_{power}w_100us_dt1000ns_overlay.i"
CONTENT="""# Legacy9: EI2067 superelastic return to O2(X), +0.977 eV/electron
[FunctorMaterials]
  [legacy9_2067_target]
    type = ADParsedFunctorMaterial
    property_name = c_O2s_EI2067
    functor_names = 'rho_neutral w_O2s'
    functor_symbols = 'rho w'
    expression = 'rho*w/0.032'
    block = plasma
  []
  [legacy9_2067_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = 'private_rates/EI-2067_O2_a1Delta.txt'
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O2s_EI2067
    reaction_progress = R_EI2067
    block = plasma
  []
  [legacy9_2067_o2s_sink]
    type = ADParsedFunctorMaterial
    property_name = S_O2s_mass_EI2067
    functor_names = 'R_EI2067'
    functor_symbols = 'R'
    expression = '-0.032*R'
    block = plasma
  []
  [legacy9_2067_constrained_o2_source]
    type = ADParsedFunctorMaterial
    property_name = S_O2_implicit_EI2067
    functor_names = 'R_EI2067'
    functor_symbols = 'R'
    expression = '0.032*R'
    block = plasma
  []
  [legacy9_2067_energy_gain]
    type = ADParsedFunctorMaterial
    property_name = S_energy_EI2067
    functor_names = 'R_EI2067'
    functor_symbols = 'R'
    expression = '0.977*R'
    block = plasma
  []
  [legacy9_2067_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_mass_closure_EI2067
    functor_names = 'S_O2s_mass_EI2067 S_O2_implicit_EI2067'
    functor_symbols = 'a b'
    expression = 'a+b'
    block = plasma
  []
[]
[FVKernels]
  [legacy9_2067_species_sink]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O2s
    source = S_O2s_mass_EI2067
    block = plasma
  []
[]
[Kernels]
  [legacy9_2067_electron_gain]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_EI2067
    functor_on_rhs = true
    block = plasma
  []
[]
[Postprocessors]
  [legacy9_2067_rate_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_EI2067
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [legacy9_2067_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_mass_closure_EI2067
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""
def overlay_ok(s):
    required=("reaction_progress = R_EI2067","rate_table_file = 'private_rates/EI-2067_O2_a1Delta.txt'",
              "variable = w_O2s","source = S_O2s_mass_EI2067",
              "expression = '-0.032*R'","expression = '0.032*R'",
              "expression = '0.977*R'","functor_on_rhs = true")
    if any(x not in s for x in required): raise ValueError("EI2067 overlay incomplete")
    if s.count("reaction_progress = R_EI2067")!=1: raise ValueError("duplicate rate owner")
    if s.count("functor_on_rhs = true")!=1: raise ValueError("energy source ownership")
def table_ok(path):
    if not path.is_file(): raise FileNotFoundError(path)
    rows=[]
    for line in path.read_text().splitlines():
        line=line.split("#")[0].strip()
        if not line: continue
        vals=line.split()
        if len(vals)!=2: raise ValueError("EI2067 rate columns")
        e,k=map(float,vals)
        if not(math.isfinite(e) and math.isfinite(k) and e>0 and k>=0):
            raise ValueError("EI2067 invalid rate")
        if rows and e<=rows[-1][0]: raise ValueError("EI2067 unordered mean energy")
        rows.append((e,k))
    if len(rows)!=100: raise ValueError("EI2067 lookup requires 100 rows")
    return rows
def verify(power):
    if (os.environ.get("OXYGEN_RESEARCH_EI2738_FORMULA")!="1" or
        os.environ.get("OXYGEN_RESEARCH_FULL24")!="0" or
        os.environ.get("OXYGEN_RESEARCH_LUMPED_O2A")!="0"):
        raise ValueError("Legacy9 incompatible research flags")
    l8=legacy8();l7=l8.l7();m=l7.legacy6()
    m.check_input(power)
    l7.validate_overlay(l7.overlay_path(m,power).read_text())
    l8.overlay_ok(l8.overlay(power).read_text())
    overlay_ok(overlay(power).read_text())
    table_ok(rate());l8.table_ok(l8.rate())
    j=json.loads((m.result(power)/"legacy6_latest_variant.json").read_text())
    if not(j.get("variant")=="LEGACY9_EI2067_from_Legacy8" and
           j.get("chemistry_channels")==NINE and
           j.get("ei407_lookup_sha256")==l8.digest(l8.rate()) and
           j.get("ei2067_lookup_sha256")==digest(rate()) and
           j.get("physics_source_sha")==BASE_SHA and
           j.get("native_initialization")=="fresh_not_restarted" and
           j.get("scientific_acceptance")=="HOLD"):
        raise ValueError("Legacy9 provenance mismatch")
    print("LEGACY9_EI2067_P0_PASS",power,digest(rate()))
    return l8,l7,m,j
def prepare(power):
    l8=legacy8();l8.prepare(power)
    source=Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/RATE_NAME
    rows=table_ok(source); reference=table_ok(l8.rate())
    if any(not math.isclose(a[0],b[0],rel_tol=1e-10,abs_tol=1e-10)
           for a,b in zip(rows,reference)): raise ValueError("EI407/EI2067 rate grids mismatch")
    dest=rate();dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and digest(dest)!=digest(source): raise ValueError("EI2067 private rate conflict")
    shutil.copyfile(source,dest)
    target=overlay(power)
    if target.exists(): raise ValueError("refuse EI2067 overlay overwrite")
    overlay_ok(CONTENT);target.write_text(CONTENT)
    l7=l8.l7();m=l7.legacy6();record=m.result(power)/"legacy6_latest_variant.json"
    j=json.loads(record.read_text())
    if j["chemistry_channels"]!=l8.EIGHT: raise ValueError("Legacy8 baseline changed")
    j.update({"variant":"LEGACY9_EI2067_from_Legacy8","chemistry_channels":NINE,
        "rate_origin":"Legacy8 source plus private EI2067 lookup",
        "ei2067_lookup_filename":RATE_NAME,"ei2067_lookup_sha256":digest(dest),
        "ei2067_energy_gain_eV":0.977,
        "ei2067_rate_origin":"Oxygen25 private 100-point lookup; SCIENCE_HOLD",
        "scientific_acceptance":"HOLD"})
    record.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    verify(power);print("LEGACY9_EI2067_PREPARED",power)
def patch(power):
    l8,l7,m,j=verify(power)
    path=m.CHEM/"issue397_l1_power_scan_replay.sh"
    old=path.read_text()
    check=l8.CHECK_OLD+" '$EI407_OVERLAY' '$EI2067_OVERLAY'"
    solve="${O2A_EXTRA_INPUT} ${EI2738_EXTRA_INPUT} '$EI407_OVERLAY' '$EI2067_OVERLAY' Outputs/file_base='$RESULT/run/plasma'"
    if old.count(l8.CHECK_OLD)!=1 or old.count(l8.SOLVE_OLD)!=1 or check in old or solve in old:
        raise ValueError("pinned replay argv altered")
    new=old.replace(l8.CHECK_OLD,check,1).replace(l8.SOLVE_OLD,solve,1)
    if new.count(check)!=1 or new.count(solve)!=1: raise ValueError("EI2067 missing from native commands")
    path.write_text(new)
    (m.result(power)/"legacy9_argv_patch.json").write_text(json.dumps({
        "power_W":power,"old_sha256":hashlib.sha256(old.encode()).hexdigest(),
        "patched_sha256":hashlib.sha256(new.encode()).hexdigest(),
        "physics_input_changed":False,"scientific_acceptance":"HOLD"},indent=2)+"\n")
    print("LEGACY9_EI2067_P2_P3_ARGV_PASS",power)
def archive(power):
    l8,l7,m,j=verify(power)
    m.PERSIST=tuple(m.PERSIST)+(l7.overlay_path(m,power).name,l8.overlay(power).name,overlay(power).name)
    m.verify_and_archive(power)
    path=m.result(power)/"legacy6_restart_100000ns_manifest.json"
    saved=json.loads(path.read_text())
    if not(saved["chemistry_channels"]==NINE and saved["native_endpoint_s"]==1e-4
       and saved["verified_full_native_100us_checkpoint"]): raise ValueError("Legacy9 endpoint invalid")
    paths=[x["path"] for x in saved["inventory"]["inputs"]]
    for p in (l7.overlay_path(m,power),l8.overlay(power),overlay(power)):
        if not any(x.endswith("/"+p.name) for x in paths): raise ValueError("missing chemistry input")
    if any("private_rates" in p for p in paths): raise ValueError("private lookup leaked")
    saved.update({"restart_requires_exact_legacy6_chemistry":False,
                  "restart_requires_exact_legacy9_chemistry":True,
                  "ei407_recovery_rate_sha256":j["ei407_lookup_sha256"],
                  "ei2067_recovery_private_rate_required":RATE_NAME,
                  "ei2067_recovery_rate_sha256":j["ei2067_lookup_sha256"]})
    path.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("LEGACY9_EI2067_NATIVE_100US_PASS",power)
def self_test():
    l8=legacy8()
    assert NINE==l8.EIGHT+["EI-2067"]
    overlay_ok(CONTENT)
    for bad in (CONTENT.replace("reaction_progress = R_EI2067","reaction_progress = R_BAD"),
                CONTENT.replace("variable = w_O2s","variable = w_O")):
        try: overlay_ok(bad)
        except ValueError: pass
        else: raise AssertionError("EI2067 overlay negative control failed")
    print("LEGACY9_EI2067_HARNESS_SELFTEST_PASS")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    for arg in ("self-test","prepare-variant","verify-nine","patch-replay-argv","verify-and-archive"):
        g.add_argument("--"+arg,action="store_true")
    p.add_argument("--power-w",type=int,choices=(400,1000))
    a=p.parse_args()
    if a.self_test:self_test()
    elif a.power_w is None:p.error("--power-w required")
    elif a.prepare_variant:prepare(a.power_w)
    elif a.verify_nine:verify(a.power_w)
    elif a.patch_replay_argv:patch(a.power_w)
    else:archive(a.power_w)
