#!/usr/bin/env python3
"""Fresh 0-100us 11-channel EI943-only extension to Legacy8+EI417+EI935.

Exact comparison source: Run 41739266674. Difference: -EI2259 +EI943.
No EI2058, EI2259, H05, EI2072, EI2074. Research-only scientific HOLD.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil
from pathlib import Path
CHEM=Path("experiments/Issue395_powered_chemistry_ladder")
RATE="EI-943_O_1D.txt"
LOSS_EV=-1.967
EXCLUDED={"H05","EI-2058","EI-2259","EI-2072","EI-2074"}
NEW_ID="EI-943"
VARIANT="LEGACY8_EI417_EI935_EI943_NO_EI2058_NO_EI2259_NO_HOLD"

CONTENT="""# Oxygen EI943: e + O(1D) -> e + O(3P), superelastic.
# Source: original private EI-943_O_1D.txt, single native rate owner.
# O(1D) is existing w_Os; O(3P) is existing w_O.
# Energy gain +1.967 eV * R, no net electron particle source.
[FunctorMaterials]
  [ei943_excited_o_target]
    type = ADParsedFunctorMaterial
    property_name = c_Os_EI943
    functor_names = 'rho_neutral w_Os'
    functor_symbols = 'rho wos'
    expression = 'rho*wos/0.016'
    block = plasma
  []
  [ei943_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = 'private_rates/EI-943_O_1D.txt'
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_Os_EI943
    reaction_progress = R_EI943
    block = plasma
  []
  [ei943_excited_o_sink]
    type = ADParsedFunctorMaterial
    property_name = S_Os_mass_EI943
    functor_names = 'R_EI943'
    functor_symbols = 'R'
    expression = '-0.016*R'
    block = plasma
  []
  [ei943_ground_o_birth]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_EI943
    functor_names = 'R_EI943'
    functor_symbols = 'R'
    expression = '0.016*R'
    block = plasma
  []
  [ei943_electron_energy_gain]
    type = ADParsedFunctorMaterial
    property_name = S_energy_EI943
    functor_names = 'R_EI943'
    functor_symbols = 'R'
    expression = '1.967*R'
    block = plasma
  []
  [ei943_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_mass_closure_EI943
    functor_names = 'S_Os_mass_EI943 S_O_mass_EI943'
    functor_symbols = 'a b'
    expression = 'a+b'
    block = plasma
  []
[]
[FVKernels]
  [ei943_excited_o]
    type = PhysicsFVSpeciesReactionSource
    variable = w_Os
    source = S_Os_mass_EI943
    block = plasma
  []
  [ei943_ground_o]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_EI943
    block = plasma
  []
[]
[Kernels]
  [ei943_electron_energy]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_EI943
    functor_on_rhs = true
    block = plasma
  []
[]
[Postprocessors]
  [ei943_rate_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_EI943
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei943_energy_gain_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_energy_EI943
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei943_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_mass_closure_EI943
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""


def load_parent():
    path=Path(os.environ.get("EI935","_legacy6_control/.github/scripts/oxygen_legacy8_ei417_ei935_no_hold_100us.py"))
    spec=importlib.util.spec_from_file_location("ei935_parent",path)
    if spec is None or spec.loader is None: raise FileNotFoundError(path)
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def rate():return CHEM/"private_rates"/RATE
def overlay(power):return CHEM/f"ei943_atomic_superelastic_{power}w_100us_dt1000ns_overlay.i"
def expected(parent):return list(parent.CHANNELS)+[NEW_ID]

def validate(src):
    for token in ("reaction_progress = R_EI943","rate_table_file = 'private_rates/EI-943_O_1D.txt'",
            "target_molar_concentration = c_Os_EI943","functor_names = 'rho_neutral w_Os'",
            "\n    variable = w_Os\n","\n    variable = w_O\n","\n    variable = log_energy\n",
            "expression = '-0.016*R'","expression = '0.016*R'",
            "expression = '1.967*R'","expression = 'a+b'",
            "source = S_Os_mass_EI943","source = S_O_mass_EI943",
            "functor = S_energy_EI943"):
        if token not in src:raise ValueError("EI943 missing "+token)
    if src.count("reaction_progress = R_EI943")!=1 or src.count("functor_on_rhs = true")!=1:
        raise ValueError("EI943 duplicate rate owner or energy kernel")
    if any(x in src for x in ("\n    variable = log_ne\n","\n    variable = log_ni\n",
            "\n    variable = log_nop\n","\n    variable = log_nm\n","\n    variable = p\n",
            "R_H05","R_EI2058","R_EI2259","R_EI2072","R_EI2074")):
        raise ValueError("EI943 touches a charged or excluded species")

def verify(power):
    p=load_parent(); b=p.l8();l7=b.l7();m=l7.legacy6()
    for k,v in (("OXYGEN_RESEARCH_EI2738_FORMULA","1"),
                ("OXYGEN_RESEARCH_FULL24","0"),("OXYGEN_RESEARCH_LUMPED_O2A","0")):
        if os.environ.get(k)!=v:raise ValueError("invalid research flag "+k)
    m.check_input(power)
    l7.validate_overlay(l7.overlay_path(m,power).read_text())
    b.overlay_ok(b.overlay(power).read_text())
    if p.f417(power).read_text()!=p.c417():raise ValueError("EI417 overlay altered")
    p.validate_935(p.f935(power).read_text())
    validate(overlay(power).read_text())
    names=(b.RATE,p.R417,p.R935,RATE)
    checks={n:b.table_ok(CHEM/"private_rates"/n) for n in names}
    j=json.loads((m.result(power)/"legacy6_latest_variant.json").read_text())
    if len(expected(p))!=11 or j.get("chemistry_channels")!=expected(p):
        raise ValueError("not exact 11-channel run")
    if EXCLUDED.intersection(j["chemistry_channels"]):
        raise ValueError("held or excluded chemistry active")
    if any((j.get("variant")!=VARIANT,j.get("native_initialization")!="fresh_not_restarted",
            j.get("physics_source_sha")!="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab",
            j.get("scientific_acceptance")!="HOLD",j.get("ei943_energy_loss_eV")!=LOSS_EV,
            j.get("ei943_lookup_sha256")!=checks[RATE],
            j.get("ei407_lookup_sha256")!=checks[b.RATE],
            j.get("ei417_lookup_sha256")!=checks[p.R417],
            j.get("ei935_lookup_sha256")!=checks[p.R935],
            any(k.startswith(("ei2058_","ei2259_")) for k in j))):
        raise ValueError("11-channel provenance mismatch")
    print("EI943_11CH_P0_PASS",power,checks[RATE])
    return p,b,l7,m,j

def prepare(power):
    p=load_parent()
    p.prepare(power)
    b=p.l8()
    src=Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/RATE
    checksum=b.table_ok(src)
    dst=rate();dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists() and digest(dst)!=checksum:raise ValueError("EI943 rate conflict")
    shutil.copyfile(src,dst)
    f=overlay(power)
    if f.exists():raise ValueError("EI943 overlay already exists")
    validate(CONTENT)
    f.write_text(CONTENT)
    m=b.l7().legacy6()
    path=m.result(power)/"legacy6_latest_variant.json"
    j=json.loads(path.read_text())
    if j.get("chemistry_channels")!=p.CHANNELS:raise ValueError("not exact 10ch parent")
    j.update({"variant":VARIANT,"chemistry_channels":expected(p),
        "hold_excluded":sorted(EXCLUDED),"ei943_reaction":"e + O(1D) -> e + O(3P)",
        "ei943_rate_source":"original private 100-point Oxygen25 HPEM EI943 lookup",
        "ei943_lookup_filename":RATE,"ei943_lookup_sha256":checksum,
        "ei943_energy_loss_eV":LOSS_EV,"ei943_rate_mode":"original_private_EEDF_mean_energy_lookup",
        "ei943_reverse_of":"EI-935","ei943_branching_and_detailed_balance":"science_HOLD",
        "scientific_acceptance":"HOLD"})
    path.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    verify(power)
    print("EI943_11CH_PREPARED",power)

def patch(power):
    p,b,l7,m,j=verify(power)
    script=m.CHEM/"issue397_l1_power_scan_replay.sh"
    before=script.read_text()
    new_check=p.NEW_CHECK+" '$EI943_OVERLAY'"
    new_solve=p.NEW_SOLVE.replace(" Outputs/file_base="," '$EI943_OVERLAY' Outputs/file_base=")
    if before.count(p.OLD_CHECK)!=1 or before.count(p.OLD_SOLVE)!=1:
        raise ValueError("original replay command mismatch")
    if any(t in before for t in ("$EI407_OVERLAY","$EI417_OVERLAY","$EI935_OVERLAY",
            "$EI943_OVERLAY","$EI2058_OVERLAY","$EI2259_OVERLAY",
            "$H05_OVERLAY","$EI2072_OVERLAY","$EI2074_OVERLAY")):
        raise ValueError("replay previously modified")
    after=before.replace(p.OLD_CHECK,new_check,1).replace(p.OLD_SOLVE,new_solve,1)
    if after.count(new_check)!=1 or after.count(new_solve)!=1:raise ValueError("patch count invalid")
    if "$EI2058_OVERLAY" in after or "$EI2259_OVERLAY" in after:
        raise ValueError("excluded chemistry in replay")
    script.write_text(after)
    (m.result(power)/"ei943_only_argv_patch.json").write_text(json.dumps({
        "power_W":power,"source_sha256":hashlib.sha256(before.encode()).hexdigest(),
        "patched_sha256":hashlib.sha256(after.encode()).hexdigest(),
        "overlays":["EI-2738","EI-407","EI-417","EI-935","EI-943"],
        "excluded":sorted(EXCLUDED),"scientific_acceptance":"HOLD"},indent=2)+"\n")
    print("EI943_11CH_ARGV_PASS",power)

def archive(power):
    p,b,l7,m,j=verify(power)
    files=(l7.overlay_path(m,power),b.overlay(power),p.f417(power),p.f935(power),overlay(power))
    m.PERSIST=tuple(m.PERSIST)+tuple(f.name for f in files)
    m.verify_and_archive(power)
    path=m.result(power)/"legacy6_restart_100000ns_manifest.json"
    saved=json.loads(path.read_text())
    if any((not saved.get("verified_full_native_100us_checkpoint"),
            saved.get("native_endpoint_s")!=1e-4,
            saved.get("chemistry_channels")!=expected(p),saved.get("variant")!=VARIANT,
            saved.get("scientific_acceptance")!="HOLD",
            bool(EXCLUDED.intersection(saved.get("chemistry_channels",[]))))):
        raise ValueError("native 100us or 11ch endpoint not verified")
    inputs=[item["path"] for item in saved["inventory"]["inputs"]]
    for f in files:
        if not any(x.endswith("/"+f.name) for x in inputs):
            raise ValueError("missing archived overlay "+f.name)
    if any("private_rates" in x or any(t in x.lower() for t in (
            "h05_associative","ei2058_o2a","ei2259_o2plus","ei2072_o2a","ei2074_o2a"))
            for x in inputs):
        raise ValueError("private rate or excluded input in archive")
    saved.update({"restart_requires_exact_ei417_ei935_ei943_chemistry":True,
        "restart_requires_exact_legacy6_chemistry":False,"hold_excluded":sorted(EXCLUDED),
        "ei943_recovery_private_rate_required":RATE,
        "ei943_recovery_rate_sha256":j["ei943_lookup_sha256"],
        "ei943_energy_loss_eV":LOSS_EV,"ei943_scientific_status":"HOLD"})
    for k,n in (("ei407",b.RATE),("ei417",p.R417),("ei935",p.R935)):
        saved[k+"_recovery_private_rate_required"]=n
        saved[k+"_recovery_rate_sha256"]=j[k+"_lookup_sha256"]
    path.write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    print("EI943_11CH_NATIVE_100US_PASS",power)

def self_test():
    p=load_parent();p.self_test()
    assert len(set(expected(p)))==len(expected(p))==11
    assert not EXCLUDED.intersection(expected(p))
    validate(CONTENT)
    for corrupt in (CONTENT.replace("reaction_progress = R_EI943","reaction_progress = R_INVALID"),
            CONTENT.replace("variable = w_Os","variable = w_O2s"),
            CONTENT.replace("expression = '1.967*R'","expression = '-1.967*R'"),
            CONTENT.replace("expression = 'a+b'","expression = 'a-b'")):
        try:validate(corrupt)
        except ValueError:pass
        else:raise AssertionError("EI943 mutation not rejected")
    print("EI943_11CH_SELFTEST_PASS")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    for name in ("self-test","prepare-variant","verify-eleven","patch-replay-argv","verify-and-archive"):
        group.add_argument("--"+name,action="store_true")
    parser.add_argument("--power-w",type=int,choices=(400,1000))
    args=parser.parse_args()
    if args.self_test:self_test()
    elif args.power_w is None:parser.error("--power-w required")
    elif args.prepare_variant:prepare(args.power_w)
    elif args.verify_eleven:verify(args.power_w)
    elif args.patch_replay_argv:patch(args.power_w)
    else:archive(args.power_w)
