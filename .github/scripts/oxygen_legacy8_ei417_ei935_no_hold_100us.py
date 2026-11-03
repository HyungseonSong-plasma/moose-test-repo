#!/usr/bin/env python3
"""Isolated fresh 0-100us Legacy8 + EI417 + EI935 (10ch), HOLD H05/EI2072/EI2074."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,shutil
from pathlib import Path
CHEM=Path("experiments/Issue395_powered_chemistry_ladder")
BASE=["EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20","EI-2738","EI-407"]
CHANNELS=BASE+["EI-417","EI-935"]
FORBIDDEN={"H05","EI-2072","EI-2074"}
R417="EI-417_O2_X.txt"
R935="EI-935_O_3P.txt"
OLD_CHECK="'$OELASTIC' ${O2A_EXTRA_INPUT} ${EI2738_EXTRA_INPUT}"
OLD_SOLVE="Outputs/file_base='$RESULT/run/plasma' ${O2A_EXTRA_INPUT} ${EI2738_EXTRA_INPUT}"
NEW_CHECK=OLD_CHECK+" '$EI407_OVERLAY' '$EI417_OVERLAY' '$EI935_OVERLAY'"
NEW_SOLVE="${O2A_EXTRA_INPUT} ${EI2738_EXTRA_INPUT} '$EI407_OVERLAY' '$EI417_OVERLAY' '$EI935_OVERLAY' Outputs/file_base='$RESULT/run/plasma'"
EI935="""# EI-935 e + O(3P) -> e + O(1D); 1.967 eV electron energy loss.
[FunctorMaterials]
  [ei935_target]
    type = ADParsedFunctorMaterial
    property_name = c_O_EI935
    functor_names = 'rho_neutral w_O'
    functor_symbols = 'rho wo'
    expression = 'rho*wo/0.016'
    block = plasma
  []
  [ei935_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = 'private_rates/EI-935_O_3P.txt'
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O_EI935
    reaction_progress = R_EI935
    block = plasma
  []
  [ei935_o_sink]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_EI935
    functor_names = 'R_EI935'
    functor_symbols = 'R'
    expression = '-0.016*R'
    block = plasma
  []
  [ei935_os_birth]
    type = ADParsedFunctorMaterial
    property_name = S_Os_mass_EI935
    functor_names = 'R_EI935'
    functor_symbols = 'R'
    expression = '0.016*R'
    block = plasma
  []
  [ei935_energy_sink]
    type = ADParsedFunctorMaterial
    property_name = S_energy_EI935
    functor_names = 'R_EI935'
    functor_symbols = 'R'
    expression = '-1.967*R'
    block = plasma
  []
  [ei935_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_mass_closure_EI935
    functor_names = 'S_O_mass_EI935 S_Os_mass_EI935'
    functor_symbols = 'a b'
    expression = 'a+b'
    block = plasma
  []
[]
[FVKernels]
  [ei935_o]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_EI935
    block = plasma
  []
  [ei935_os]
    type = PhysicsFVSpeciesReactionSource
    variable = w_Os
    source = S_Os_mass_EI935
    block = plasma
  []
[]
[Kernels]
  [ei935_e_energy]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_EI935
    functor_on_rhs = true
    block = plasma
  []
[]
[Postprocessors]
  [ei935_R_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_EI935
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei935_energy_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_energy_EI935
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei935_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_mass_closure_EI935
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    if not spec or not spec.loader: raise FileNotFoundError(path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m
def l8():
    return module(Path(os.environ.get("LEGACY8","_legacy6_control/.github/scripts/oxygen_legacy8_ei407_100us.py")),"legacy8_nohold")
def c417():
    m=module(Path(os.environ.get("EI417_SOURCE","_legacy6_control/.github/scripts/oxygen_legacy8_h05_ei417_100us.py")),"existing_ei417_content")
    txt=m.CONTENT.replace("legacy8_h05_ei417","legacy8_ei417").replace("Legacy8+H05","Legacy8")
    if "legacy8_h05" in txt.lower() or txt.count("reaction_progress = R_EI417")!=1:
        raise ValueError("EI417 source unexpectedly references H05 or duplicate progress")
    return txt
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def r(name):return CHEM/"private_rates"/name
def f417(power):return CHEM/f"ei417_without_h05_{power}w_100us_dt1000ns_overlay.i"
def f935(power):return CHEM/f"ei935_atomic_excitation_{power}w_100us_dt1000ns_overlay.i"
def validate_935(s):
    for x in ("reaction_progress = R_EI935","private_rates/EI-935_O_3P.txt",
              "target_molar_concentration = c_O_EI935","variable = w_O",
              "variable = w_Os","variable = log_energy","expression = '-0.016*R'",
              "expression = '0.016*R'","expression = '-1.967*R'",
              "expression = 'a+b'","functor = S_energy_EI935"):
        if x not in s:raise ValueError("EI935 missing "+x)
    if s.count("reaction_progress = R_EI935")!=1 or s.count("functor_on_rhs = true")!=1:
        raise ValueError("EI935 duplicated or energy missing")
    if any(x in s for x in ("variable = log_ne","variable = log_nop","variable = log_ni","variable = log_nm")):
        raise ValueError("EI935 must not generate charged particles")
def verify(power):
    b=l8();l7=b.l7();m=l7.legacy6()
    if (os.environ.get("OXYGEN_RESEARCH_EI2738_FORMULA")!="1" or
        os.environ.get("OXYGEN_RESEARCH_FULL24")!="0" or
        os.environ.get("OXYGEN_RESEARCH_LUMPED_O2A")!="0"):
        raise ValueError("unexpected experiment flags")
    m.check_input(power)
    l7.validate_overlay(l7.overlay_path(m,power).read_text())
    b.overlay_ok(b.overlay(power).read_text())
    if f417(power).read_text()!=c417():raise ValueError("EI417 changed")
    validate_935(f935(power).read_text())
    digests={n:b.table_ok(r(n)) for n in (b.RATE,R417,R935)}
    j=json.loads((m.result(power)/"legacy6_latest_variant.json").read_text())
    if j.get("chemistry_channels")!=CHANNELS or FORBIDDEN.intersection(j["chemistry_channels"]):
        raise ValueError("wrong chemistry or HOLD active")
    if any((j.get("variant")!="LEGACY8_EI417_EI935_NO_HOLD",
            j.get("scientific_acceptance")!="HOLD",
            j.get("native_initialization")!="fresh_not_restarted",
            j.get("physics_source_sha")!="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab",
            j.get("ei407_lookup_sha256")!=digests[b.RATE],
            j.get("ei417_lookup_sha256")!=digests[R417],
            j.get("ei935_lookup_sha256")!=digests[R935],
            j.get("ei935_energy_loss_eV")!=1.967)):
        raise ValueError("experiment provenance mismatch")
    print("NO_HOLD_EI935_P0_PASS",power)
    return b,l7,m,j
def prepare(power):
    b=l8();b.prepare(power)
    for name in (R417,R935):
        src=Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/name
        digest=b.table_ok(src)
        dest=r(name);dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and sha(dest)!=digest:raise ValueError("private rate conflict")
        shutil.copyfile(src,dest)
    for path,txt in ((f417(power),c417()),(f935(power),EI935)):
        if path.exists():raise ValueError("refuse overlay overwrite")
        path.write_text(txt)
    validate_935(EI935)
    l7=b.l7();m=l7.legacy6()
    path=m.result(power)/"legacy6_latest_variant.json"
    j=json.loads(path.read_text())
    if j.get("chemistry_channels")!=BASE:raise ValueError("not exact Legacy8 parent")
    j.update({"variant":"LEGACY8_EI417_EI935_NO_HOLD","chemistry_channels":CHANNELS,
        "hold_excluded":sorted(FORBIDDEN),
        "ei417_lookup_filename":R417,"ei417_lookup_sha256":sha(r(R417)),
        "ei417_energy_loss_eV":17.0,
        "ei935_lookup_filename":R935,"ei935_lookup_sha256":sha(r(R935)),
        "ei935_energy_loss_eV":1.967,
        "ei935_product":"O(1D) = w_Os, distinct from O(1S)",
        "scientific_acceptance":"HOLD"})
    path.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    verify(power)
def patch(power):
    b,l7,m,j=verify(power)
    path=m.CHEM/"issue397_l1_power_scan_replay.sh"
    old=path.read_text()
    if old.count(OLD_CHECK)!=1 or old.count(OLD_SOLVE)!=1:
        raise ValueError("replay script diverged")
    if any(t in old for t in ("$H05_OVERLAY","$EI417_OVERLAY","$EI2072_OVERLAY","$EI2074_OVERLAY","$EI935_OVERLAY")):
        raise ValueError("unexpected chemistry prior to patch")
    fixed=old.replace(OLD_CHECK,NEW_CHECK,1).replace(OLD_SOLVE,NEW_SOLVE,1)
    if fixed.count(NEW_CHECK)!=1 or fixed.count(NEW_SOLVE)!=1:
        raise ValueError("wrong patched command")
    path.write_text(fixed)
    (m.result(power)/"ei935_no_hold_argv_patch.json").write_text(json.dumps({
        "power_W":power,
        "source_sha256":hashlib.sha256(old.encode()).hexdigest(),
        "patched_sha256":hashlib.sha256(fixed.encode()).hexdigest(),
        "overlays":["EI-2738","EI-407","EI-417","EI-935"],
        "exclusions":sorted(FORBIDDEN)},indent=2)+"\n")
    print("NO_HOLD_EI935_ARGV_PASS",power)
def archive(power):
    b,l7,m,j=verify(power)
    m.PERSIST=tuple(m.PERSIST)+(l7.overlay_path(m,power).name,
        b.overlay(power).name,f417(power).name,f935(power).name)
    m.verify_and_archive(power)
    path=m.result(power)/"legacy6_restart_100000ns_manifest.json"
    saved=json.loads(path.read_text())
    if not (saved["chemistry_channels"]==CHANNELS and
        saved["verified_full_native_100us_checkpoint"] and
        saved["native_endpoint_s"]==1e-4 and saved["scientific_acceptance"]=="HOLD"):
        raise ValueError("100us endpoint wrong")
    inventory=[i["path"] for i in saved["inventory"]["inputs"]]
    for f in (l7.overlay_path(m,power),b.overlay(power),f417(power),f935(power)):
        if not any(x.endswith("/"+f.name) for x in inventory):raise ValueError("missing "+f.name)
    if any("private_rates" in x or any(y in x for y in ("h05_associative_","ei2072_o2a_","ei2074_o2a_"))
           for x in inventory):
        raise ValueError("secret or HOLD overlay in checkpoint")
    saved.update({"restart_requires_exact_legacy8_ei417_ei935_chemistry":True,
        "restart_requires_exact_legacy6_chemistry":False,
        "hold_excluded":sorted(FORBIDDEN)})
    for key,name in (("ei407",b.RATE),("ei417",R417),("ei935",R935)):
        saved[key+"_recovery_private_rate_required"]=name
        saved[key+"_recovery_rate_sha256"]=j[key+"_lookup_sha256"]
    path.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("NO_HOLD_EI935_NATIVE_100US_PASS",power)
def self_test():
    assert len(CHANNELS)==10 and not FORBIDDEN.intersection(CHANNELS)
    validate_935(EI935);c417()
    for bad in (EI935.replace("reaction_progress = R_EI935","reaction_progress = R_WRONG"),
                EI935.replace("variable = w_Os","variable = w_O2s"),
                EI935.replace("expression = '-1.967*R'","expression = '1.967*R'")):
        try:validate_935(bad)
        except ValueError:pass
        else:raise AssertionError("negative validator")
    print("NO_HOLD_EI935_SELFTEST_PASS")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    for k in ("self-test","prepare-variant","verify-ten","patch-replay-argv","verify-and-archive"):
        g.add_argument("--"+k,action="store_true")
    p.add_argument("--power-w",type=int,choices=[400,1000])
    a=p.parse_args()
    if a.self_test:self_test()
    elif a.power_w is None:p.error("power required")
    elif a.prepare_variant:prepare(a.power_w)
    elif a.verify_ten:verify(a.power_w)
    elif a.patch_replay_argv:patch(a.power_w)
    else:archive(a.power_w)
