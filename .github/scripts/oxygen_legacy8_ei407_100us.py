#!/usr/bin/env python3
"""Legacy8 = Legacy7 + EI-407 only, research-only, SCIENCE_HOLD."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, os, shutil
from pathlib import Path

ROOT=Path("experiments/Issue395_powered_chemistry_ladder")
SEVEN=["EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20","EI-2738"]
EIGHT=SEVEN+["EI-407"]
RATE="EI-407_O2_X.txt"
CHECK_OLD="'$OELASTIC' ${O2A_EXTRA_INPUT} ${EI2738_EXTRA_INPUT}"
SOLVE_OLD="Outputs/file_base='$RESULT/run/plasma' ${O2A_EXTRA_INPUT} ${EI2738_EXTRA_INPUT}"
CHECK_NEW=CHECK_OLD+" '$EI407_OVERLAY'"
SOLVE_NEW="${O2A_EXTRA_INPUT} ${EI2738_EXTRA_INPUT} '$EI407_OVERLAY' Outputs/file_base='$RESULT/run/plasma'"

def l7():
    path=Path(os.environ.get("LEGACY7","_legacy7_control/.github/scripts/oxygen_legacy7_ei2738_100us.py"))
    spec=importlib.util.spec_from_file_location("control_legacy7",path)
    if spec is None or spec.loader is None: raise RuntimeError("Legacy7 harness missing")
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def overlay(power): return ROOT/f"ei407_only_{power}w_100us_dt1000ns_overlay.i"
def rate(): return ROOT/"private_rates"/RATE

def table_ok(path):
    if not path.is_file(): raise FileNotFoundError(path)
    rows=[]
    for line in path.read_text().splitlines():
        x=line.split("#")[0].strip()
        if not x: continue
        parts=x.split()
        if len(parts)!=2: raise ValueError("wrong EI407 table columns")
        e,k=map(float,parts)
        if not(math.isfinite(e) and math.isfinite(k) and e>0 and k>=0):
            raise ValueError("bad EI407 numbers")
        if rows and e<=rows[-1][0]: raise ValueError("unordered EI407 grid")
        rows.append((e,k))
    if len(rows)!=100: raise ValueError("EI407 requires 100 rate rows")
    return digest(path)

CONTENT="""# Legacy8 single EI407 excitation O2(X) -> O2(a1Delta), 0.977 eV loss
[FunctorMaterials]
  [legacy8_407_o2_target]
    type = ADParsedFunctorMaterial
    property_name = c_O2_EI407
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w'
    expression = 'rho*w/0.032'
    block = plasma
  []
  [legacy8_407_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = 'private_rates/EI-407_O2_X.txt'
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O2_EI407
    reaction_progress = R_EI407
    block = plasma
  []
  [legacy8_407_o2s_mass]
    type = ADParsedFunctorMaterial
    property_name = S_O2s_mass_EI407
    functor_names = 'R_EI407'
    functor_symbols = 'R'
    expression = '0.032*R'
    block = plasma
  []
  [legacy8_407_o2_constrained_sink]
    type = ADParsedFunctorMaterial
    property_name = S_O2_implicit_EI407
    functor_names = 'R_EI407'
    functor_symbols = 'R'
    expression = '-0.032*R'
    block = plasma
  []
  [legacy8_407_energy]
    type = ADParsedFunctorMaterial
    property_name = S_energy_EI407
    functor_names = 'R_EI407'
    functor_symbols = 'R'
    expression = '-0.977*R'
    block = plasma
  []
  [legacy8_407_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_mass_closure_EI407
    functor_names = 'S_O2s_mass_EI407 S_O2_implicit_EI407'
    functor_symbols = 'a b'
    expression = 'a+b'
    block = plasma
  []
[]
[FVKernels]
  [legacy8_407_o2s]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O2s
    source = S_O2s_mass_EI407
    block = plasma
  []
[]
[Kernels]
  [legacy8_407_electron_energy]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_EI407
    functor_on_rhs = true
    block = plasma
  []
[]
[Postprocessors]
  [legacy8_407_rate_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_EI407
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [legacy8_407_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_mass_closure_EI407
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""

def overlay_ok(source):
    for s in ("reaction_progress = R_EI407","rate_table_file = 'private_rates/EI-407_O2_X.txt'",
              "variable = w_O2s","variable = log_energy","expression = '-0.977*R'",
              "source = S_O2s_mass_EI407","expression = '-0.032*R'"):
        if s not in source: raise ValueError("EI407 incomplete: "+s)
    if source.count("reaction_progress = R_EI407")!=1: raise ValueError("duplicate EI407 owner")
    if source.count("functor_on_rhs = true")!=1: raise ValueError("bad EI407 energy owner")

def verify(power):
    if (os.environ.get("OXYGEN_RESEARCH_EI2738_FORMULA")!="1" or
        os.environ.get("OXYGEN_RESEARCH_FULL24")!="0" or
        os.environ.get("OXYGEN_RESEARCH_LUMPED_O2A")!="0"):
        raise ValueError("Legacy8 flags incompatible")
    c=l7(); m=c.legacy6()
    m.check_input(power)
    c.validate_overlay(c.overlay_path(m,power).read_text())
    overlay_ok(overlay(power).read_text())
    rate_sha=table_ok(rate())
    manifest=m.result(power)/"legacy6_latest_variant.json"
    j=json.loads(manifest.read_text())
    if not(j.get("variant")=="LEGACY8_EI407_from_Legacy7" and
           j.get("chemistry_channels")==EIGHT and
           j.get("ei407_lookup_sha256")==rate_sha and
           j.get("scientific_acceptance")=="HOLD" and
           j.get("native_initialization")=="fresh_not_restarted" and
           j.get("physics_source_sha")=="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"):
        raise ValueError("wrong Legacy8 provenance")
    print("LEGACY8_EI407_P0_PASS",power,rate_sha)
    return c,m,j

def prepare(power):
    c=l7();m=c.legacy6()
    c.prepare_variant(power)
    p=Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/RATE
    d=table_ok(p)
    dst=rate()
    dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists() and digest(dst)!=d: raise ValueError("private EI407 conflict")
    shutil.copyfile(p,dst)
    path=overlay(power)
    if path.exists(): raise ValueError("refuse overlay overwrite")
    overlay_ok(CONTENT)
    path.write_text(CONTENT)
    record=m.result(power)/"legacy6_latest_variant.json"
    j=json.loads(record.read_text())
    if j.get("chemistry_channels")!=SEVEN: raise ValueError("wrong Legacy7 baseline")
    j.update({"variant":"LEGACY8_EI407_from_Legacy7","chemistry_channels":EIGHT,
       "rate_origin":"Legacy7 rates plus private EI407 lookup",
       "ei407_lookup_filename":RATE,"ei407_lookup_sha256":d,
       "ei407_energy_loss_eV":0.977,"ei407_rate_origin":"Oxygen25 private rate; science HOLD",
       "scientific_acceptance":"HOLD"})
    record.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    verify(power)
    print("LEGACY8_EI407_PREPARED",power)

def patch(power):
    verify(power)
    c=l7(); m=c.legacy6()
    path=m.CHEM/"issue397_l1_power_scan_replay.sh"
    source=path.read_text()
    if (source.count(CHECK_OLD)!=1 or source.count(SOLVE_OLD)!=1 or
        CHECK_NEW in source or SOLVE_NEW in source):
        raise ValueError("pinned replay command mismatch")
    fixed=source.replace(CHECK_OLD,CHECK_NEW,1).replace(SOLVE_OLD,SOLVE_NEW,1)
    if fixed.count(CHECK_NEW)!=1 or fixed.count(SOLVE_NEW)!=1:
        raise ValueError("failed EI407 argv patch")
    path.write_text(fixed)
    (m.result(power)/"legacy8_argv_patch.json").write_text(json.dumps({
        "power_W":power,"original_sha256":hashlib.sha256(source.encode()).hexdigest(),
        "new_sha256":hashlib.sha256(fixed.encode()).hexdigest(),
        "physics_input_changed":False,"scientific_acceptance":"HOLD"},indent=2)+"\n")
    print("LEGACY8_EI407_ARGV_PASS",power)

def archive(power):
    c,m,j=verify(power)
    m.PERSIST=tuple(m.PERSIST)+(c.overlay_path(m,power).name,overlay(power).name)
    m.verify_and_archive(power)
    path=m.result(power)/"legacy6_restart_100000ns_manifest.json"
    saved=json.loads(path.read_text())
    if not(saved["chemistry_channels"]==EIGHT and
           saved["native_endpoint_s"]==1e-4 and
           saved["verified_full_native_100us_checkpoint"]):
        raise ValueError("Legacy8 100us endpoint failed")
    names=[p["path"] for p in saved["inventory"]["inputs"]]
    for target in (c.overlay_path(m,power),overlay(power)):
        if not any(n.endswith("/"+target.name) for n in names):
            raise ValueError("missing overlay from archive")
    if any("private_rates" in n for n in names):
        raise ValueError("private rates cannot be archived")
    saved.update({"restart_requires_exact_legacy6_chemistry":False,
        "restart_requires_exact_legacy8_chemistry":True,
        "ei407_recovery_private_rate_required":RATE,
        "ei407_recovery_rate_sha256":j["ei407_lookup_sha256"]})
    path.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("LEGACY8_EI407_NATIVE_100US_PASS",power)

def self_test():
    assert len(EIGHT)==8 and set(EIGHT)==set(SEVEN)|{"EI-407"}
    overlay_ok(CONTENT)
    for wrong in (CONTENT.replace("reaction_progress = R_EI407","reaction_progress = R_BAD"),
                  CONTENT.replace("variable = w_O2s","variable = w_O")):
        try: overlay_ok(wrong)
        except ValueError: pass
        else: raise AssertionError("negative overlay validation failed")
    print("LEGACY8_EI407_SELFTEST_PASS")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    for flag in ("self-test","prepare-variant","verify-eight","patch-replay-argv","verify-and-archive"):
        g.add_argument("--"+flag,action="store_true")
    p.add_argument("--power-w",type=int,choices=(400,1000))
    a=p.parse_args()
    if a.self_test: self_test()
    elif a.power_w is None: p.error("--power-w required")
    elif a.prepare_variant: prepare(a.power_w)
    elif a.verify_eight: verify(a.power_w)
    elif a.patch_replay_argv: patch(a.power_w)
    else: archive(a.power_w)
